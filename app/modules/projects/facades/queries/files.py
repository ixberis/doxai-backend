# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/queries/files.py

Consultas de archivos de proyecto: list_files, get_file_by_id, count_files.
Ahora async para compatibilidad con AsyncSession.

Autor: Ixchel Beristain
Fecha: 2025-10-26 (async 2025-12-27)
"""

from uuid import UUID
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models.project_file_models import ProjectFile


# Límite máximo para prevenir queries abusivas
MAX_LIMIT = 200


async def list_files(
    db: AsyncSession,
    project_id: UUID,
    limit: int = 100,
    offset: int = 0,
    include_total: bool = False
) -> List[ProjectFile] | Tuple[List[ProjectFile], int]:
    """
    Lista archivos de un proyecto.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        project_id: ID del proyecto
        limit: Número máximo de resultados (default: 100, max: MAX_LIMIT)
        offset: Desplazamiento para paginación (default: 0)
        include_total: Si True, devuelve (items, total_count)
        
    Returns:
        Lista de archivos o tupla (archivos, total) si include_total=True
    """
    # Imponer límite máximo
    effective_limit = min(limit, MAX_LIMIT)
    
    query = select(ProjectFile).where(ProjectFile.project_id == project_id)
    
    # Si se requiere total, calcularlo antes del limit/offset
    total = None
    if include_total:
        count_query = select(func.count(ProjectFile.id)).where(ProjectFile.project_id == project_id)
        total = await db.scalar(count_query) or 0
    
    query = query.order_by(ProjectFile.created_at.desc())
    query = query.offset(offset).limit(effective_limit)
    
    result = await db.execute(query)
    items = list(result.scalars().all())
    
    return (items, total) if include_total else items


async def get_file_by_id(db: AsyncSession, file_id: UUID) -> Optional[ProjectFile]:
    """
    Obtiene un archivo por ID.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        file_id: ID del archivo
        
    Returns:
        Archivo o None si no existe
    """
    result = await db.get(ProjectFile, file_id)
    return result


async def count_files_by_project(db: AsyncSession, project_id: UUID) -> int:
    """
    Cuenta archivos de un proyecto.
    
    Args:
        db: Sesión AsyncSession SQLAlchemy
        project_id: ID del proyecto
        
    Returns:
        Número de archivos en el proyecto
    """
    query = select(func.count(ProjectFile.id)).where(
        ProjectFile.project_id == project_id
    )
    
    return await db.scalar(query) or 0


__all__ = [
    "list_files",
    "get_file_by_id",
    "count_files_by_project",
    "MAX_LIMIT",
]
