# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/queries/audit.py

Consultas de logs de auditoría: ProjectActionLog, ProjectFileEventLog.
Ahora async para compatibilidad con AsyncSession.

Autor: Ixchel Beristain
Fecha: 2025-10-26 (async 2025-12-27)
"""

from uuid import UUID
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models.project_action_log_models import ProjectActionLog
from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


# Límite máximo para prevenir queries abusivas
MAX_LIMIT = 200


async def list_actions(
    db: AsyncSession,
    project_id: UUID,
    action_type: Optional[ProjectActionType] = None,
    limit: int = 100,
    offset: int = 0
) -> List[ProjectActionLog]:
    """
    Lista acciones de auditoría de un proyecto.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        project_id: ID del proyecto
        action_type: Filtro opcional por tipo de acción
        limit: Número máximo de resultados (default: 100, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        
    Returns:
        Lista de logs de acción ordenados por fecha descendente
    """
    # Imponer límite máximo
    effective_limit = min(limit, MAX_LIMIT)
    
    query = select(ProjectActionLog).where(
        ProjectActionLog.project_id == project_id
    )
    
    if action_type is not None:
        query = query.where(ProjectActionLog.action_type == action_type)
    
    query = query.order_by(ProjectActionLog.created_at.desc())
    query = query.offset(offset).limit(effective_limit)
    
    result = await db.execute(query)
    return list(result.scalars().all())


async def list_file_events(
    db: AsyncSession,
    project_id: UUID,
    file_id: Optional[UUID] = None,
    event_type: Optional[ProjectFileEvent] = None,
    limit: int = 100,
    offset: int = 0
) -> List[ProjectFileEventLog]:
    """
    Lista eventos de archivos de un proyecto.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        project_id: ID del proyecto
        file_id: Filtro opcional por archivo específico
        event_type: Filtro opcional por tipo de evento
        limit: Número máximo de resultados (default: 100, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        
    Returns:
        Lista de eventos de archivo ordenados por fecha descendente
    """
    # Imponer límite máximo
    effective_limit = min(limit, MAX_LIMIT)
    
    query = select(ProjectFileEventLog).where(
        ProjectFileEventLog.project_id == project_id
    )
    
    if file_id is not None:
        query = query.where(ProjectFileEventLog.project_file_id == file_id)
    
    if event_type is not None:
        query = query.where(ProjectFileEventLog.event_type == event_type)
    
    query = query.order_by(ProjectFileEventLog.created_at.desc())
    query = query.offset(offset).limit(effective_limit)
    
    result = await db.execute(query)
    return list(result.scalars().all())


__all__ = [
    "list_actions",
    "list_file_events",
    "MAX_LIMIT",
]
