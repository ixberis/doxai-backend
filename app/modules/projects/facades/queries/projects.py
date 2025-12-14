# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/queries/projects.py

Consultas de proyectos: get_by_id, get_by_slug, list_by_user, etc.

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

from uuid import UUID
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus


# Límite máximo para prevenir queries abusivas
MAX_LIMIT = 200


def get_by_id(db: Session, project_id: UUID) -> Optional[Project]:
    """
    Obtiene un proyecto por ID.
    
    Args:
        db: Sesión SQLAlchemy
        project_id: ID del proyecto
        
    Returns:
        Proyecto o None si no existe
    """
    return db.get(Project, project_id)


def get_by_slug(db: Session, slug: str) -> Optional[Project]:
    """
    Obtiene un proyecto por slug.
    
    Usa índice único en project_slug para búsqueda rápida.
    
    Args:
        db: Sesión SQLAlchemy
        slug: Slug del proyecto (globalmente único)
        
    Returns:
        Proyecto o None si no existe
    """
    return db.scalar(
        select(Project).where(Project.project_slug == slug)
    )


def list_by_user(
    db: Session,
    user_id: UUID,
    state: Optional[ProjectState] = None,
    status: Optional[ProjectStatus] = None,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False
) -> List[Project] | Tuple[List[Project], int]:
    """
    Lista proyectos de un usuario con filtros opcionales.
    
    Usa índice idx_projects_user_state para búsquedas eficientes.
    
    Args:
        db: Sesión SQLAlchemy
        user_id: ID del usuario propietario
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
    
    query = select(Project).where(Project.user_id == user_id)
    
    if state is not None:
        query = query.where(Project.state == state)
    
    if status is not None:
        query = query.where(Project.status == status)
    
    # Si se requiere total, calcularlo antes del limit/offset
    total = None
    if include_total:
        count_query = select(func.count(Project.id)).where(Project.user_id == user_id)
        if state is not None:
            count_query = count_query.where(Project.state == state)
        if status is not None:
            count_query = count_query.where(Project.status == status)
        total = db.scalar(count_query) or 0
    
    query = query.order_by(Project.created_at.desc())
    query = query.offset(offset).limit(effective_limit)
    
    items = list(db.execute(query).scalars().all())
    
    return (items, total) if include_total else items


def list_ready_projects(
    db: Session,
    user_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    include_total: bool = False
) -> List[Project] | Tuple[List[Project], int]:
    """
    Lista proyectos en estado 'ready'.
    
    Usa índice parcial idx_projects_ready_at_ready para optimización.
    
    Args:
        db: Sesión SQLAlchemy
        user_id: Filtro opcional por usuario
        limit: Número máximo de resultados (default: 50, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, devuelve (items, total_count)
        
    Returns:
        Lista de proyectos listos o tupla (proyectos, total) si include_total=True
    """
    # Imponer límite máximo
    effective_limit = min(limit, MAX_LIMIT)
    
    query = select(Project).where(Project.state == ProjectState.ready)
    
    if user_id is not None:
        query = query.where(Project.user_id == user_id)
    
    # Si se requiere total, calcularlo antes del limit/offset
    total = None
    if include_total:
        count_query = select(func.count(Project.id)).where(Project.state == ProjectState.ready)
        if user_id is not None:
            count_query = count_query.where(Project.user_id == user_id)
        total = db.scalar(count_query) or 0
    
    query = query.order_by(Project.ready_at.desc())
    query = query.offset(offset).limit(effective_limit)
    
    items = list(db.execute(query).scalars().all())
    
    return (items, total) if include_total else items


def count_projects_by_user(
    db: Session,
    user_id: UUID,
    state: Optional[ProjectState] = None,
    status: Optional[ProjectStatus] = None
) -> int:
    """
    Cuenta proyectos de un usuario con filtros opcionales.
    
    Args:
        db: Sesión SQLAlchemy
        user_id: ID del usuario
        state: Filtro opcional por estado
        status: Filtro opcional por status
        
    Returns:
        Número de proyectos que cumplen los criterios
    """
    query = select(func.count(Project.id)).where(Project.user_id == user_id)
    
    if state is not None:
        query = query.where(Project.state == state)
    
    if status is not None:
        query = query.where(Project.status == status)
    
    return db.scalar(query) or 0


__all__ = [
    "get_by_id",
    "get_by_slug",
    "list_by_user",
    "list_ready_projects",
    "count_projects_by_user",
    "MAX_LIMIT",
]
