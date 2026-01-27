
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/repositories/project_file_event_log_repository.py

Repositorio para la bitácora de eventos de archivos de proyecto
(ProjectFileEventLog).

BD 2.0 SSOT (2026-01-27):
- file_id referencia files_base (Files 2.0), NO project_files
- event_metadata (JSONB) en lugar de columnas snapshot legacy
- Eliminadas columnas: project_file_id, user_id, user_email, snapshots

Responsabilidades:
- Registrar eventos sobre archivos (uploaded, validated, moved, deleted)
- Consultar eventos por proyecto o por archivo

Autor: Ixchel Beristáin
Fecha: 2025-11-21
Actualizado: 2026-01-27 - BD 2.0 SSOT
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.modules.projects.models import ProjectFileEventLog
from app.modules.projects.enums import ProjectFileEvent


def log_project_file_event(
    db: Session,
    *,
    project_id: UUID,
    file_id: UUID,
    event_type: ProjectFileEvent,
    event_metadata: Optional[Dict[str, Any]] = None,
) -> ProjectFileEventLog:
    """
    Registra un evento sobre un archivo de proyecto.
    
    BD 2.0 SSOT:
    - file_id referencia files_base (Files 2.0)
    - event_metadata almacena datos adicionales en JSONB

    Args:
        project_id: ID del proyecto.
        file_id: ID del archivo (files_base.file_id).
        event_type: Tipo de evento (uploaded, validated, moved, deleted).
        event_metadata: Metadata adicional del evento en formato JSONB.

    Returns:
        Instancia persistida de ProjectFileEventLog.
    """
    event = ProjectFileEventLog(
        project_id=project_id,
        file_id=file_id,
        event_type=event_type,
        event_metadata=event_metadata or {},
    )
    db.add(event)
    db.flush()
    db.commit()
    db.refresh(event)
    return event


def list_project_file_events(
    db: Session,
    *,
    project_id: Optional[UUID] = None,
    file_id: Optional[UUID] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[ProjectFileEventLog]:
    """
    Lista eventos de archivos, filtrando opcionalmente por proyecto y/o archivo.
    Ordena de más reciente a más antiguo.
    
    BD 2.0: file_id referencia files_base.
    """
    q = db.query(ProjectFileEventLog)

    if project_id is not None:
        q = q.filter(ProjectFileEventLog.project_id == project_id)
    if file_id is not None:
        q = q.filter(ProjectFileEventLog.file_id == file_id)

    q = q.order_by(desc(ProjectFileEventLog.created_at)).offset(offset).limit(limit)
    return list(q.all())


__all__ = [
    "log_project_file_event",
    "list_project_file_events",
]

# Fin del archivo backend/app/modules/projects/repositories/project_file_event_log_repository.py