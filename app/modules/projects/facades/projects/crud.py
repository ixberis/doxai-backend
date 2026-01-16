# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/projects/crud.py

Operaciones CRUD de proyectos: create, update, delete.
Incluye validación de slug y whitelist de campos.

BD 2.0 SSOT:
- auth_user_id: UUID canónico de ownership (reemplaza user_id legacy)

Transacciones: Usa commit_or_raise como única fuente de verdad.
Runtime: AsyncSession only (producción).

Autor: Ixchel Beristain
Fecha: 2025-10-26
Actualizado: 2026-01-16 - Async-only, tx unificado en commit_or_raise
"""

from uuid import UUID
from typing import Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.facades.errors import ProjectNotFound, SlugAlreadyExists, PermissionDenied
from app.modules.projects.facades.base import commit_or_raise
from app.modules.projects.facades.audit_logger import AuditLogger


# Lista blanca de campos permitidos en update()
ALLOWED_UPDATE_FIELDS: Set[str] = {
    "project_name",
    "project_description"
}


async def _get_for_update(db: AsyncSession, project_id: UUID) -> Project:
    """
    Obtiene un proyecto para actualización con bloqueo pesimista.
    """
    result = await db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    project = result.scalars().first()
    
    if not project:
        raise ProjectNotFound(project_id)
    return project


async def create(
    db: AsyncSession,
    audit: AuditLogger,
    *,
    user_id: UUID,  # Parámetro legacy, se mapea a auth_user_id en BD 2.0
    user_email: str,
    name: str,
    slug: str,
    description: Optional[str] = None
) -> Project:
    """
    Crea un nuevo proyecto.
    
    Reglas de negocio:
    - project_slug es único POR USUARIO (auth_user_id, project_slug)
    - Slug se normaliza (lower, strip) antes de validación
    - Estado inicial: created
    - Status inicial: in_process
    - Registra acción 'created' en auditoría
    
    BD 2.0 SSOT: user_id param se mapea a auth_user_id column.
    Transacciones: commit_or_raise maneja commit/rollback.
    
    Args:
        db: AsyncSession SQLAlchemy
        audit: Logger de auditoría
        user_id: UUID del usuario propietario (se almacena como auth_user_id)
        user_email: Email del usuario propietario
        name: Nombre del proyecto
        slug: Slug único del proyecto
        description: Descripción opcional del proyecto
        
    Returns:
        Instancia de Project creada y persistida
        
    Raises:
        SlugAlreadyExists: Si el slug ya existe PARA ESTE USUARIO
    """
    normalized_slug = slug.strip().lower()
    
    async def _work() -> Project:
        # BD 2.0 SSOT: Validar unicidad del slug POR USUARIO
        result = await db.execute(
            select(Project).where(
                Project.auth_user_id == user_id,
                Project.project_slug == normalized_slug
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise SlugAlreadyExists(normalized_slug)
        
        # BD 2.0 SSOT: user_id param → auth_user_id column
        project = Project(
            auth_user_id=user_id,
            project_name=name,
            project_slug=normalized_slug,
            project_description=description,
            state=ProjectState.created,
            status=ProjectStatus.in_process,
        )
        
        db.add(project)
        await db.flush()
        
        # Registrar acción de creación
        audit.log_action(
            project_id=project.id,
            auth_user_id=user_id,
            action_type=ProjectActionType.created,
            action_metadata={"name": name, "slug": normalized_slug}
        )
        
        return project
    
    try:
        return await commit_or_raise(db, _work)
    except IntegrityError as e:
        # Capturar carreras de condición en slug único
        if "project_slug" in str(e.orig):
            raise SlugAlreadyExists(normalized_slug)
        raise


async def update(
    db: AsyncSession,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,
    user_email: str,
    enforce_owner: bool = True,
    **changes
) -> Project:
    """
    Actualiza metadatos de un proyecto (nombre, descripción, etc.).
    
    No debe usarse para cambiar state o status (usar métodos específicos).
    Solo permite actualizar campos de la lista blanca ALLOWED_UPDATE_FIELDS.
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    Transacciones: commit_or_raise maneja commit/rollback.
    """
    async def _work() -> Project:
        project = await _get_for_update(db, project_id)
        
        # BD 2.0 SSOT: comparar con auth_user_id
        if enforce_owner and project.auth_user_id != user_id:
            raise PermissionDenied(f"Usuario {user_id} no es propietario del proyecto {project_id}")
        
        # Filtrar solo campos permitidos (lista blanca)
        allowed_changes = {k: v for k, v in changes.items() if k in ALLOWED_UPDATE_FIELDS}
        
        # Construir metadata con detalles de cambios
        change_details = {}
        for key, value in allowed_changes.items():
            old_value = getattr(project, key, None)
            change_details[key] = {"from": old_value, "to": value}
            setattr(project, key, value)
        
        # Registrar acción con detalles
        audit.log_action(
            project_id=project.id,
            auth_user_id=user_id,
            action_type=ProjectActionType.updated,
            action_metadata={"changes": change_details}
        )
        
        return project
    
    return await commit_or_raise(db, _work)


async def delete(
    db: AsyncSession,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,
    user_email: str,
    enforce_owner: bool = True
) -> bool:
    """
    Elimina un proyecto (hard delete).
    
    NOTA: Para eliminación de cara al usuario, usa archive() en su lugar.
    Este método debe reservarse para limpieza administrativa.
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    Transacciones: commit_or_raise maneja commit/rollback.
    """
    async def _work() -> bool:
        project = await _get_for_update(db, project_id)
        
        # BD 2.0 SSOT: comparar con auth_user_id
        if enforce_owner and project.auth_user_id != user_id:
            raise PermissionDenied(f"Usuario {user_id} no es propietario del proyecto {project_id}")
        
        # Registrar acción antes de eliminar
        audit.log_action(
            project_id=project.id,
            auth_user_id=user_id,
            action_type=ProjectActionType.deleted,
            action_metadata={"name": project.project_name, "slug": project.project_slug}
        )
        
        # Eliminar proyecto
        await db.delete(project)
        return True
    
    return await commit_or_raise(db, _work)


__all__ = [
    "create",
    "update",
    "delete",
    "ALLOWED_UPDATE_FIELDS",
]
