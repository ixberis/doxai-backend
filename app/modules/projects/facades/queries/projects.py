# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/queries/projects.py

Consultas de proyectos: get_by_id, get_by_slug, list_by_user, etc.
Ahora async para compatibilidad con AsyncSession.

Autor: Ixchel Beristain
Fecha: 2025-10-26 (async 2025-12-27)
"""

from typing import Optional, List, Tuple
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus


# Límite máximo para prevenir queries abusivas
MAX_LIMIT = 200


async def get_by_id(db: AsyncSession, project_id: UUID) -> Optional[Project]:
    """
    Obtiene un proyecto por ID.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        project_id: ID del proyecto (UUID)
        
    Returns:
        Proyecto o None si no existe
    """
    result = await db.get(Project, project_id)
    return result


async def get_by_slug(db: AsyncSession, slug: str) -> Optional[Project]:
    """
    Obtiene un proyecto por slug.
    
    Usa índice único en project_slug para búsqueda rápida.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        slug: Slug del proyecto (globalmente único)
        
    Returns:
        Proyecto o None si no existe
    """
    stmt = select(Project).where(Project.project_slug == slug)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_user(
    db: AsyncSession,
    user_email: str,
    state: Optional[ProjectState] = None,
    status: Optional[ProjectStatus] = None,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False
) -> List[Project] | Tuple[List[Project], int]:
    """
    Lista proyectos de un usuario con filtros opcionales.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        user_email: Email del usuario propietario (filtro CITEXT)
        state: Filtro opcional por estado técnico
        status: Filtro opcional por status administrativo
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, devuelve (items, total_count)
        
    Returns:
        Lista de proyectos o tupla (proyectos, total) si include_total=True
    """
    # Imponer límite máximo
    effective_limit = min(limit, MAX_LIMIT)
    
    # HOTFIX: filtrar por user_email (str) para evitar uuid = integer error
    query = select(Project).where(Project.user_email == user_email)
    
    if state is not None:
        query = query.where(Project.state == state)
    
    if status is not None:
        query = query.where(Project.status == status)
    
    # Si se requiere total, calcularlo antes del limit/offset
    total = None
    if include_total:
        count_query = select(func.count(Project.id)).where(Project.user_email == user_email)
        if state is not None:
            count_query = count_query.where(Project.state == state)
        if status is not None:
            count_query = count_query.where(Project.status == status)
        total = await db.scalar(count_query) or 0
    
    query = query.order_by(Project.created_at.desc())
    query = query.offset(offset).limit(effective_limit)
    
    result = await db.execute(query)
    items = list(result.scalars().all())
    
    return (items, total) if include_total else items


async def list_ready_projects(
    db: AsyncSession,
    user_email: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False
) -> List[Project] | Tuple[List[Project], int]:
    """
    Lista proyectos en estado 'ready'.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        user_email: Filtro opcional por email de usuario
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, devuelve (items, total_count)
        
    Returns:
        Lista de proyectos listos o tupla (proyectos, total) si include_total=True
    """
    # Imponer límite máximo
    effective_limit = min(limit, MAX_LIMIT)
    
    query = select(Project).where(Project.state == ProjectState.ready)
    
    if user_email is not None:
        query = query.where(Project.user_email == user_email)
    
    # Si se requiere total, calcularlo antes del limit/offset
    total = None
    if include_total:
        count_query = select(func.count(Project.id)).where(Project.state == ProjectState.ready)
        if user_email is not None:
            count_query = count_query.where(Project.user_email == user_email)
        total = await db.scalar(count_query) or 0
    
    query = query.order_by(Project.ready_at.desc())
    query = query.offset(offset).limit(effective_limit)
    
    result = await db.execute(query)
    items = list(result.scalars().all())
    
    return (items, total) if include_total else items


async def list_active_projects(
    db: AsyncSession,
    user_email: str,
    order_by: str = "updated_at",
    asc: bool = False,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False,
) -> Tuple[List[Project], int]:
    """
    Lista proyectos activos (state != ARCHIVED) de un usuario con ordenamiento.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        user_email: Email del usuario propietario
        order_by: Columna para ordenar (updated_at, created_at, ready_at)
        asc: Orden ascendente (default: False = descendente)
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, ejecuta COUNT; si False, total = len(items)
        
    Returns:
        Tupla (proyectos, total_count)
    """
    effective_limit = min(limit, MAX_LIMIT)
    
    # HOTFIX: filtrar por user_email (str) para evitar uuid = integer error
    base_filter = (Project.user_email == user_email) & (Project.state != ProjectState.ARCHIVED)
    
    # Query con ordenamiento
    query = select(Project).where(base_filter)
    
    # Mapear columna de ordenamiento
    order_column = getattr(Project, order_by, Project.updated_at)
    query = query.order_by(order_column.asc() if asc else order_column.desc())
    query = query.offset(offset).limit(effective_limit)
    
    result = await db.execute(query)
    items = list(result.scalars().all())
    
    # Solo ejecutar COUNT si se requiere
    if include_total:
        count_query = select(func.count(Project.id)).where(base_filter)
        total = await db.scalar(count_query) or 0
    else:
        total = len(items)
    
    return items, total


async def list_closed_projects(
    db: AsyncSession,
    user_email: str,
    order_by: str = "updated_at",
    asc: bool = False,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False,
) -> Tuple[List[Project], int]:
    """
    Lista proyectos cerrados/archivados (state == ARCHIVED) de un usuario con ordenamiento.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        user_email: Email del usuario propietario
        order_by: Columna para ordenar (updated_at, created_at, ready_at)
        asc: Orden ascendente (default: False = descendente)
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, ejecuta COUNT; si False, total = len(items)
        
    Returns:
        Tupla (proyectos, total_count)
    """
    effective_limit = min(limit, MAX_LIMIT)
    
    # HOTFIX: filtrar por user_email (str) para evitar uuid = integer error
    base_filter = (Project.user_email == user_email) & (Project.state == ProjectState.ARCHIVED)
    
    # Query con ordenamiento
    query = select(Project).where(base_filter)
    
    # Mapear columna de ordenamiento
    order_column = getattr(Project, order_by, Project.updated_at)
    query = query.order_by(order_column.asc() if asc else order_column.desc())
    query = query.offset(offset).limit(effective_limit)
    
    result = await db.execute(query)
    items = list(result.scalars().all())
    
    # Solo ejecutar COUNT si se requiere
    if include_total:
        count_query = select(func.count(Project.id)).where(base_filter)
        total = await db.scalar(count_query) or 0
    else:
        total = len(items)
    
    return items, total


async def count_projects_by_user(
    db: AsyncSession,
    user_email: str,
    state: Optional[ProjectState] = None,
    status: Optional[ProjectStatus] = None
) -> int:
    """
    Cuenta proyectos de un usuario con filtros opcionales.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        user_email: Email del usuario
        state: Filtro opcional por estado
        status: Filtro opcional por status
        
    Returns:
        Número de proyectos que cumplen los criterios
    """
    query = select(func.count(Project.id)).where(Project.user_email == user_email)
    
    if state is not None:
        query = query.where(Project.state == state)
    
    if status is not None:
        query = query.where(Project.status == status)
    
    return await db.scalar(query) or 0


__all__ = [
    "get_by_id",
    "get_by_slug",
    "list_by_user",
    "list_ready_projects",
    "list_active_projects",
    "list_closed_projects",
    "count_projects_by_user",
    "MAX_LIMIT",
]
