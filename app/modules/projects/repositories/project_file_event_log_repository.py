
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/repositories/project_file_event_log_repository.py

Repositorio para la bitácora de eventos de archivos de proyecto
(ProjectFileEventLog).

Responsabilidades:
- Registrar eventos sobre archivos (uploaded, validated, moved, deleted)
- Consultar eventos por proyecto o por archivo

Autor: Ixchel Beristáin
Fecha: 2025-11-21
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.modules.projects.models import ProjectFileEventLog
from app.modules.projects.enums import ProjectFileEvent


def log_project_file_event(
    db: Session,
    *,
    project_id: UUID,
    project_file_id: Optional[UUID],
    event_type: ProjectFileEvent,
    user_id: Optional[UUID] = None,
    user_email: Optional[str] = None,
    details: Optional[str] = None,
    file_name: Optional[str] = None,
    file_path: Optional[str] = None,
    file_size_kb: Optional[float] = None,
    file_checksum: Optional[str] = None,
) -> ProjectFileEventLog:
    """
    Registra un evento sobre un archivo de proyecto.

    Args:
        project_id: ID del proyecto.
        project_file_id: ID del archivo de proyecto (puede ser None si no existe).
        event_type: Tipo de evento (uploaded, validated, moved, deleted).
        user_id: Usuario que ejecuta la acción (opcional).
        user_email: Email del usuario (opcional).
        details: Descripción textual (opcional).
        file_name: Nombre del archivo (snapshot).
        file_path: Ruta del archivo (snapshot).
        file_size_kb: Tamaño del archivo en KB (snapshot).
        file_checksum: Checksum del archivo (snapshot).

    Returns:
        Instancia persistida de ProjectFileEventLog.
    """
    event = ProjectFileEventLog(
        project_id=project_id,
        project_file_id=project_file_id,
        project_file_id_snapshot=project_file_id,
        user_id=user_id,
        user_email=user_email,
        event_type=event_type,
        event_details=details,
        project_file_name_snapshot=file_name or "",
        project_file_path_snapshot=file_path or "",
        project_file_size_kb_snapshot=file_size_kb,
        project_file_checksum_snapshot=file_checksum,
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
    project_file_id: Optional[UUID] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[ProjectFileEventLog]:
    """
    Lista eventos de archivos, filtrando opcionalmente por proyecto y/o archivo.
    Ordena de más reciente a más antiguo.
    """
    q = db.query(ProjectFileEventLog)

    if project_id is not None:
        q = q.filter(ProjectFileEventLog.project_id == project_id)
    if project_file_id is not None:
        q = q.filter(ProjectFileEventLog.project_file_id == project_file_id)

    q = q.order_by(desc(ProjectFileEventLog.created_at)).offset(offset).limit(limit)
    return list(q.all())


__all__ = [
    "log_project_file_event",
    "list_project_file_events",
]

# Fin del archivo backend/app/modules/projects/repositories/project_file_event_log_repository.py