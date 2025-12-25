
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
        try:
            stmt = select(func.count(literal_column("*"))).select_from(ProjectFile)
            if project_id is not None and _safe_hasattr(ProjectFile, "project_id"):
                stmt = stmt.where(ProjectFile.project_id == project_id)
            return int(self.db.execute(stmt).scalar() or 0)
        except Exception:
            return 0

    # ---------------------------------------------------------------------
    # Promedio de tamaño de archivos
    # ---------------------------------------------------------------------
    def avg_file_size_bytes(self, project_id: Optional[UUID] = None) -> Optional[float]:
        """
        Promedio de tamaño de archivo en bytes (si hay columna de tamaño).
        """
        try:
            size_col = _get_size_column()
            if size_col is None:
                return None

            stmt = select(func.avg(size_col).label("avg_size")).select_from(ProjectFile)
            if project_id is not None and _safe_hasattr(ProjectFile, "project_id"):
                stmt = stmt.where(ProjectFile.project_id == project_id)
            val = self.db.execute(stmt).scalar()
            return float(val) if val is not None else None
        except Exception:
            return None

    # ---------------------------------------------------------------------
    # Eventos de archivos por tipo
    # ---------------------------------------------------------------------
    def events_by_type(self, project_id: Optional[UUID] = None) -> ProjectFileEventsByType:
        """
        Conteo de eventos de archivos por tipo (uploaded, validated, moved, deleted, etc.).
        """
        try:
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
        except Exception:
            return ProjectFileEventsByType(items={}, total=0)

    # ---------------------------------------------------------------------
    # Últimos eventos (útil para inspección/diagnóstico)
    # ---------------------------------------------------------------------
    def last_events(self, limit: int = 50, project_id: Optional[UUID] = None) -> List[dict]:
        """
        Devuelve los últimos N eventos de archivos (ordenados por timestamp desc).
        Retorna lista de diccionarios con campos esenciales.
        
        Usa ORM para compatibilidad multi-dialecto (SQLite en tests, PostgreSQL en prod).
        En caso de error (por incompatibilidad de esquema o dialecto), retorna lista vacía.
        """
        try:
            stmt = (
                select(
                    ProjectFileEventLog.project_id,
                    ProjectFileEventLog.project_file_id,
                    cast(ProjectFileEventLog.event_type, String).label("event_type"),
                    ProjectFileEventLog.created_at,
                    ProjectFileEventLog.event_details,
                )
                .select_from(ProjectFileEventLog)
                .order_by(desc(ProjectFileEventLog.created_at))
                .limit(limit)
            )
            
            if project_id is not None:
                stmt = stmt.where(ProjectFileEventLog.project_id == project_id)
            
            rows = self.db.execute(stmt).mappings().all()
            return [dict(r) for r in rows]
        except Exception:
            # Fallback para SQLite u otros dialectos sin soporte completo
            return []

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