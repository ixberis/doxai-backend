
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/aggregators/db/files.py

Agregadores de métricas desde BD para el módulo Projects (nivel archivos).
Paridad conceptual con Payments: totales de archivos, promedios de tamaño,
conteo de eventos por tipo y consulta de últimos eventos.

Ajuste 08/11/2025:
- Implementa consultas ORM defensivas (multi-dialecto y tolerantes a esquemas).
- Si alguna columna no existe (p. ej., size_bytes), devuelve None/0 sin fallar.

Ajuste 21/11/2025 (Projects v2):
- Corrige serialización de last_events: usa 'project_file_id' en lugar de 'file_id',
  alineado con el modelo ProjectFileEventLog v2.

Autor: Ixchel Beristain
Fecha de actualización: 21/11/2025
"""
from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select, literal_column, cast, String, desc
from sqlalchemy.orm import Session

# Modelos y enums del módulo Projects
from app.modules.projects.models.project_file_models import ProjectFile  # type: ignore
from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog  # type: ignore
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent  # type: ignore

# Schemas de métricas
from app.modules.projects.metrics.schemas.metrics_schemas import (
    ProjectFilesSummary,
    ProjectFileEventsByType,
)


def _get_size_column():
    """
    Intenta resolver el nombre de columna de tamaño en ProjectFile.
    Acepta variantes comunes: size_bytes, file_size, size.
    """
    for name in ("size_bytes", "file_size", "size"):
        col = getattr(ProjectFile, name, None)
        if col is not None:
            return col
    return None


def _safe_hasattr(model, attr: str) -> bool:
    return getattr(model, attr, None) is not None


class FilesDBAggregator:
    """
    Agregador de métricas en BD para archivos y eventos de archivos.
    """

    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------------------
    # Totales de archivos
    # ---------------------------------------------------------------------
    def files_total(self, project_id: Optional[UUID] = None) -> int:
        """
        Total de archivos (global o por proyecto si se indica).
        """
        stmt = select(func.count(literal_column("*"))).select_from(ProjectFile)
        if project_id is not None and _safe_hasattr(ProjectFile, "project_id"):
            stmt = stmt.where(ProjectFile.project_id == project_id)
        return int(self.db.execute(stmt).scalar() or 0)

    # ---------------------------------------------------------------------
    # Promedio de tamaño de archivos
    # ---------------------------------------------------------------------
    def avg_file_size_bytes(self, project_id: Optional[UUID] = None) -> Optional[float]:
        """
        Promedio de tamaño de archivo en bytes (si hay columna de tamaño).
        """
        size_col = _get_size_column()
        if size_col is None:
            return None

        stmt = select(func.avg(size_col).label("avg_size")).select_from(ProjectFile)
        if project_id is not None and _safe_hasattr(ProjectFile, "project_id"):
            stmt = stmt.where(ProjectFile.project_id == project_id)
        val = self.db.execute(stmt).scalar()
        return float(val) if val is not None else None

    # ---------------------------------------------------------------------
    # Eventos de archivos por tipo
    # ---------------------------------------------------------------------
    def events_by_type(self, project_id: Optional[UUID] = None) -> ProjectFileEventsByType:
        """
        Conteo de eventos de archivos por tipo (uploaded, validated, moved, deleted, etc.).
        """
        if not _safe_hasattr(ProjectFileEventLog, "event_type"):
            # Sin columna -> vacío
            return ProjectFileEventsByType(items={}, total=0)

        stmt = select(
            cast(ProjectFileEventLog.event_type, String), func.count(literal_column("*"))
        ).select_from(ProjectFileEventLog)

        if project_id is not None and _safe_hasattr(ProjectFileEventLog, "project_id"):
            stmt = stmt.where(ProjectFileEventLog.project_id == project_id)

        stmt = stmt.group_by(ProjectFileEventLog.event_type)
        rows = self.db.execute(stmt).all()
        items: Dict[str, int] = {str(k or ""): int(v or 0) for k, v in rows}
        total = sum(items.values())
        return ProjectFileEventsByType(items=items, total=total)

    # ---------------------------------------------------------------------
    # Últimos eventos (útil para inspección/diagnóstico)
    # ---------------------------------------------------------------------
    def last_events(self, limit: int = 50, project_id: Optional[UUID] = None) -> List[dict]:
        """
        Devuelve los últimos N eventos de archivos (ordenados por timestamp desc).
        Retorna lista de diccionarios con campos esenciales.
        
        NOTA: La columna de timestamp es 'event_created_at', no 'created_at'.
        """
        from sqlalchemy import text
        
        # Usamos raw SQL porque la tabla usa 'event_created_at' en lugar de 'created_at'
        if project_id is not None:
            sql = text("""
                SELECT 
                    project_id, 
                    project_file_id, 
                    event_type,
                    event_created_at as created_at,
                    event_details
                FROM project_file_event_logs
                WHERE project_id = :project_id
                ORDER BY event_created_at DESC
                LIMIT :limit
            """)
            result = self.db.execute(sql, {"project_id": str(project_id), "limit": limit})
        else:
            sql = text("""
                SELECT 
                    project_id, 
                    project_file_id, 
                    event_type,
                    event_created_at as created_at,
                    event_details
                FROM project_file_event_logs
                ORDER BY event_created_at DESC
                LIMIT :limit
            """)
            result = self.db.execute(sql, {"limit": limit})
        
        rows = result.mappings().all()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------------
    # Resumen (para snapshot DB)
    # ---------------------------------------------------------------------
    def files_summary(self, project_id: Optional[UUID] = None) -> ProjectFilesSummary:
        """
        Construye un resumen con totales básicos y promedio de tamaños.
        """
        total_files = self.files_total(project_id=project_id)
        avg_size = self.avg_file_size_bytes(project_id=project_id)

        # Podemos interpretar "last_events_total" como recuento de eventos en ventana
        # corta; aquí tomamos limit 100 por default (ajustable).
        last_events_sample = self.last_events(limit=100, project_id=project_id)
        last_events_total = len(last_events_sample)

        return ProjectFilesSummary(
            files_total=total_files,
            last_events_total=last_events_total,
            avg_file_size_bytes=avg_size,
        )

# Fin del archivo backend/app/modules/projects/metrics/aggregators/db/files.py