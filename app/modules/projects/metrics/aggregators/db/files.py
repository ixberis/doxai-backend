
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/aggregators/db/files.py

Agregadores de métricas desde BD para el módulo Projects (nivel archivos).

BD 2.0 SSOT (2026-01-27):
- Eliminado ProjectFile (tabla project_files no existe)
- Files 2.0 es el SSOT de archivos (files_base, input_files, product_files)
- Este módulo solo agrega métricas de ProjectFileEventLog

Autor: Ixchel Beristain
Fecha de actualización: 2026-01-27
"""
from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select, literal_column, cast, String, desc
from sqlalchemy.orm import Session

# Modelos y enums del módulo Projects (BD 2.0: sin ProjectFile)
from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent

# Schemas de métricas
from app.modules.projects.metrics.schemas.metrics_schemas import (
    ProjectFilesSummary,
    ProjectFileEventsByType,
)


def _safe_hasattr(model, attr: str) -> bool:
    return getattr(model, attr, None) is not None


class FilesDBAggregator:
    """
    Agregador de métricas en BD para eventos de archivos.
    
    BD 2.0 SSOT:
    - NO hay tabla project_files (usar Files 2.0 para métricas de archivos)
    - Solo agrega métricas de ProjectFileEventLog
    """

    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------------------
    # Totales de archivos (BD 2.0: siempre 0, usar Files 2.0)
    # ---------------------------------------------------------------------
    def files_total(self, project_id: Optional[UUID] = None) -> int:
        """
        BD 2.0: project_files no existe. Retorna 0.
        Para métricas de archivos, usar el módulo Files 2.0.
        """
        return 0

    # ---------------------------------------------------------------------
    # Promedio de tamaño de archivos (BD 2.0: siempre None)
    # ---------------------------------------------------------------------
    def avg_file_size_bytes(self, project_id: Optional[UUID] = None) -> Optional[float]:
        """
        BD 2.0: project_files no existe. Retorna None.
        Para métricas de archivos, usar el módulo Files 2.0.
        """
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
        """
        try:
            stmt = (
                select(
                    ProjectFileEventLog.project_id,
                    ProjectFileEventLog.file_id,
                    cast(ProjectFileEventLog.event_type, String).label("event_type"),
                    ProjectFileEventLog.created_at,
                    ProjectFileEventLog.event_metadata,
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
            return []

    # ---------------------------------------------------------------------
    # Resumen (para snapshot DB)
    # ---------------------------------------------------------------------
    def files_summary(self, project_id: Optional[UUID] = None) -> ProjectFilesSummary:
        """
        Construye un resumen de métricas de eventos de archivos.
        
        BD 2.0: files_total y avg_file_size_bytes siempre son 0/None
        porque project_files no existe. Usar Files 2.0 para esas métricas.
        """
        total_files = self.files_total(project_id=project_id)
        avg_size = self.avg_file_size_bytes(project_id=project_id)

        last_events_sample = self.last_events(limit=100, project_id=project_id)
        last_events_total = len(last_events_sample)

        return ProjectFilesSummary(
            files_total=total_files,
            last_events_total=last_events_total,
            avg_file_size_bytes=avg_size,
        )


# Fin del archivo backend/app/modules/projects/metrics/aggregators/db/files.py