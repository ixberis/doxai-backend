
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/repositories/project_action_log_repository.py

Repositorio para la bitácora de acciones sobre proyectos (ProjectActionLog).

Responsabilidades:
- Registrar acciones (create, update, delete, cambios de estado, etc.)
- Consultar acciones por proyecto

Autor: Ixchel Beristáin
Fecha: 2025-11-21
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.modules.projects.models import ProjectActionLog
from app.modules.projects.enums import ProjectActionType


def log_project_action(
    db: Session,
    *,
    project_id: UUID,
    action_type: ProjectActionType,
    user_id: Optional[UUID] = None,
    user_email: Optional[str] = None,
    details: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ProjectActionLog:
    """
    Registra una acción sobre un proyecto.

    Args:
        project_id: ID del proyecto afectado.
        action_type: Tipo de acción (ProjectActionType).
        user_id: Usuario que ejecutó la acción (opcional).
        user_email: Email del usuario (opcional).
        details: Descripción textual corta.
        metadata: Metadatos adicionales en JSON (dict).

    Returns:
        Instancia persistida de ProjectActionLog.
    """
    log = ProjectActionLog(
        project_id=project_id,
        user_id=user_id,
        user_email=user_email,
        action_type=action_type,
        action_details=details,
        action_metadata=metadata or {},
    )
    db.add(log)
    db.flush()
    db.commit()
    db.refresh(log)
    return log


def list_project_actions(
    db: Session,
    project_id: UUID,
    *,
    limit: int = 100,
    offset: int = 0,
) -> List[ProjectActionLog]:
    """
    Lista acciones de un proyecto, ordenadas de más reciente a más antigua.
    """
    q = (
        db.query(ProjectActionLog)
        .filter(ProjectActionLog.project_id == project_id)
        .order_by(desc(ProjectActionLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    return list(q.all())


__all__ = [
    "log_project_action",
    "list_project_actions",
]

# Fin del archivo backend/app/modules/projects/repositories/project_action_log_repository.py