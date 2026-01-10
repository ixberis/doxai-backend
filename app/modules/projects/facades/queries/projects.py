# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/queries/projects.py

Consultas de proyectos: get_by_id, get_by_slug, list_by_user, etc.
Ahora async para compatibilidad con AsyncSession.

BD 2.0 SSOT Architecture (2026-01-10):
- auth_user_id (UUID): SSOT para ownership en tabla projects
- user_email: LEGACY join key, mantener solo para compatibilidad temporal

Autor: Ixchel Beristain
Fecha: 2025-10-26 (async 2025-12-27, SSOT BD 2.0 2026-01-10)
"""

import logging
import time
from typing import Optional, List, Tuple
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus

logger = logging.getLogger(__name__)

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
    
    LEGACY: Usa user_email como join key. Preferir list_by_auth_user_id para SSOT.
    
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
    
    # LEGACY: filtrar por user_email (str)
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


async def list_by_auth_user_id(
    db: AsyncSession,
    auth_user_id: UUID,
    state: Optional[ProjectState] = None,
    status: Optional[ProjectStatus] = None,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False
) -> List[Project] | Tuple[List[Project], int]:
    """
    Lista proyectos de un usuario por auth_user_id (UUID SSOT).
    
    BD 2.0 SSOT: Este es el método preferido para filtrar projects.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        auth_user_id: UUID del usuario (SSOT canónico)
        state: Filtro opcional por estado técnico
        status: Filtro opcional por status administrativo
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, devuelve (items, total_count)
        
    Returns:
        Lista de proyectos o tupla (proyectos, total) si include_total=True
    """
    effective_limit = min(limit, MAX_LIMIT)
    
    # BD 2.0 SSOT: filtrar por projects.auth_user_id (UUID)
    query = select(Project).where(Project.auth_user_id == auth_user_id)
    
    if state is not None:
        query = query.where(Project.state == state)
    
    if status is not None:
        query = query.where(Project.status == status)
    
    total = None
    if include_total:
        count_query = select(func.count(Project.id)).where(Project.auth_user_id == auth_user_id)
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


async def list_by_user_id(
    db: AsyncSession,
    user_id: UUID,  # BD 2.0 SSOT: DEBE ser UUID, no int
    state: Optional[ProjectState] = None,
    status: Optional[ProjectStatus] = None,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False
) -> List[Project] | Tuple[List[Project], int]:
    """
    Lista proyectos de un usuario por auth_user_id (UUID).
    
    BD 2.0 SSOT: Este método es un alias de list_by_auth_user_id.
    El parámetro se llama user_id por compatibilidad con firmas legacy,
    pero DEBE recibir un UUID (auth_user_id).
    
    ⚠️ DEPRECATED: Usar list_by_auth_user_id directamente para nuevas integraciones.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        user_id: UUID del usuario (SSOT auth_user_id). ❌ NO pasar int.
        state: Filtro opcional por estado técnico
        status: Filtro opcional por status administrativo
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, devuelve (items, total_count)
        
    Returns:
        Lista de proyectos o tupla (proyectos, total) si include_total=True
    """
    effective_limit = min(limit, MAX_LIMIT)
    
    # BD 2.0 SSOT: user_id param → auth_user_id column
    query = select(Project).where(Project.auth_user_id == user_id)
    
    if state is not None:
        query = query.where(Project.state == state)
    
    if status is not None:
        query = query.where(Project.status == status)
    
    total = None
    if include_total:
        count_query = select(func.count(Project.id)).where(Project.auth_user_id == user_id)
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
    auth_user_id: UUID = None,
    user_email: str = None,
    order_by: str = "updated_at",
    asc: bool = False,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False,
) -> Tuple[List[Project], int]:
    """
    Lista proyectos activos (state != ARCHIVED) de un usuario con ordenamiento.
    
    BD 2.0 SSOT: Preferir auth_user_id. user_email solo para compat legacy.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        auth_user_id: UUID del usuario (SSOT, preferido)
        user_email: Email del usuario (legacy, solo si auth_user_id no está disponible)
        order_by: Columna para ordenar (updated_at, created_at, ready_at)
        asc: Orden ascendente (default: False = descendente)
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, ejecuta COUNT; si False, total = len(items)
        
    Returns:
        Tupla (proyectos, total_count)
    """
    start = time.perf_counter()
    effective_limit = min(limit, MAX_LIMIT)
    
    # BD 2.0 SSOT: preferir auth_user_id (UUID), fallback a user_email
    if auth_user_id is not None:
        base_filter = (Project.auth_user_id == auth_user_id) & (Project.state != ProjectState.ARCHIVED)
        user_log = f"auth_user_id={str(auth_user_id)[:8]}..."
    elif user_email is not None:
        base_filter = (Project.user_email == user_email) & (Project.state != ProjectState.ARCHIVED)
        user_log = f"user_email={user_email[:3]}***"
        logger.debug("list_active_projects using legacy user_email filter")
    else:
        raise ValueError("Must provide auth_user_id or user_email")
    
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
    
    duration_ms = (time.perf_counter() - start) * 1000
    if duration_ms > 500:
        logger.warning(
            "query_slow operation=list_active_projects %s count=%d duration_ms=%.2f",
            user_log, len(items), duration_ms
        )
    else:
        logger.debug(
            "query_completed operation=list_active_projects %s count=%d duration_ms=%.2f",
            user_log, len(items), duration_ms
        )
    
    return items, total


async def list_closed_projects(
    db: AsyncSession,
    auth_user_id: UUID = None,
    user_email: str = None,
    order_by: str = "updated_at",
    asc: bool = False,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False,
) -> Tuple[List[Project], int]:
    """
    Lista proyectos cerrados/archivados (state == ARCHIVED) de un usuario con ordenamiento.
    
    BD 2.0 SSOT: Preferir auth_user_id. user_email solo para compat legacy.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        auth_user_id: UUID del usuario (SSOT, preferido)
        user_email: Email del usuario (legacy, solo si auth_user_id no está disponible)
        order_by: Columna para ordenar (updated_at, created_at, ready_at)
        asc: Orden ascendente (default: False = descendente)
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, ejecuta COUNT; si False, total = len(items)
        
    Returns:
        Tupla (proyectos, total_count)
    """
    start = time.perf_counter()
    effective_limit = min(limit, MAX_LIMIT)
    
    # BD 2.0 SSOT: preferir auth_user_id (UUID), fallback a user_email
    if auth_user_id is not None:
        base_filter = (Project.auth_user_id == auth_user_id) & (Project.state == ProjectState.ARCHIVED)
        user_log = f"auth_user_id={str(auth_user_id)[:8]}..."
    elif user_email is not None:
        base_filter = (Project.user_email == user_email) & (Project.state == ProjectState.ARCHIVED)
        user_log = f"user_email={user_email[:3]}***"
        logger.debug("list_closed_projects using legacy user_email filter")
    else:
        raise ValueError("Must provide auth_user_id or user_email")
    
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
    
    duration_ms = (time.perf_counter() - start) * 1000
    if duration_ms > 500:
        logger.warning(
            "query_slow operation=list_closed_projects %s count=%d duration_ms=%.2f",
            user_log, len(items), duration_ms
        )
    else:
        logger.debug(
            "query_completed operation=list_closed_projects %s count=%d duration_ms=%.2f",
            user_log, len(items), duration_ms
        )
    
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
    "list_by_user_id",
    "list_by_auth_user_id",
    "list_ready_projects",
    "list_active_projects",
    "list_closed_projects",
    "count_projects_by_user",
    "MAX_LIMIT",
]
