# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/projects/crud.py

Operaciones CRUD de proyectos: create, update, delete.
Incluye validación de slug y whitelist de campos.

BD 2.0 SSOT:
- auth_user_id: UUID canónico de ownership (reemplaza user_id legacy)

Autor: Ixchel Beristain
Fecha: 2025-10-26
Actualizado: 2026-01-10 - BD 2.0 SSOT: user_id → auth_user_id
"""

from uuid import UUID
from typing import Optional, Set
from sqlalchemy.orm import Session
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


def create(
    db: Session,
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
    - project_slug es globalmente único
    - Slug se normaliza (lower, strip) antes de validación
    - Estado inicial: created
    - Status inicial: in_process
    - Registra acción 'created' en auditoría
    
    BD 2.0 SSOT: user_id param se mapea a auth_user_id column.
    
    Args:
        db: Sesión SQLAlchemy
        audit: Logger de auditoría
        user_id: UUID del usuario propietario (se almacena como auth_user_id)
        user_email: Email del usuario propietario
        name: Nombre del proyecto
        slug: Slug único del proyecto
        description: Descripción opcional del proyecto
        
    Returns:
        Instancia de Project creada y persistida
        
    Raises:
        SlugAlreadyExists: Si el slug ya existe en la base de datos
    """
    def _work():
        # Normalizar slug (defensa contra duplicados por casing/espacios)
        normalized_slug = slug.strip().lower()
        
        # Validar unicidad del slug (global)
        existing = db.scalar(
            select(Project).where(Project.project_slug == normalized_slug)
        )
        if existing:
            raise SlugAlreadyExists(normalized_slug)
        
        # BD 2.0 SSOT: user_id param → auth_user_id column
        project = Project(
            auth_user_id=user_id,
            user_email=user_email,
            project_name=name,
            project_slug=normalized_slug,
            project_description=description,
            state=ProjectState.created,
            status=ProjectStatus.in_process,
        )
        
        db.add(project)
        db.flush()
        
        # Registrar acción de creación
        audit.log_action(
            project_id=project.id,
            user_id=user_id,
            user_email=user_email,
            action=ProjectActionType.created,
            metadata={"name": name, "slug": normalized_slug}
        )
        
        return project
    
    try:
        return commit_or_raise(db, _work)
    except IntegrityError as e:
        # Capturar carreras de condición en slug único
        if "project_slug" in str(e.orig):
            raise SlugAlreadyExists(slug.strip().lower())
        raise


def update(
    db: Session,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,  # Parámetro legacy, se compara con auth_user_id en BD 2.0
    user_email: str,
    enforce_owner: bool = True,
    **changes
) -> Project:
    """
    Actualiza metadatos de un proyecto (nombre, descripción, etc.).
    
    No debe usarse para cambiar state o status (usar métodos específicos).
    Solo permite actualizar campos de la lista blanca ALLOWED_UPDATE_FIELDS.
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    
    Args:
        db: Sesión SQLAlchemy
        audit: Logger de auditoría
        project_id: ID del proyecto a actualizar
        user_id: UUID del usuario que realiza la actualización
        user_email: Email del usuario que realiza la actualización
        enforce_owner: Si True, valida que user_id sea el propietario
        **changes: Campos a actualizar (ej. project_name, project_description)
        
    Returns:
        Proyecto actualizado
        
    Raises:
        ProjectNotFound: Si el proyecto no existe
        PermissionDenied: Si enforce_owner=True y el usuario no es propietario
    """
    def _work():
        project = _get_for_update(db, project_id)
        
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
            user_id=user_id,
            user_email=user_email,
            action=ProjectActionType.updated,
            metadata={"changes": change_details}
        )
        
        return project
    
    return commit_or_raise(db, _work)


def delete(
    db: Session,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,  # Parámetro legacy, se compara con auth_user_id en BD 2.0
    user_email: str,
    enforce_owner: bool = True
) -> bool:
    """
    Elimina un proyecto (hard delete).
    
    NOTA: Para eliminación de cara al usuario, usa archive() en su lugar.
    Este método debe reservarse para limpieza administrativa.
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    
    Args:
        db: Sesión SQLAlchemy
        audit: Logger de auditoría
        project_id: ID del proyecto a eliminar
        user_id: UUID del usuario que realiza la eliminación
        user_email: Email del usuario
        enforce_owner: Si True, valida que user_id sea el propietario
        
    Returns:
        True si se eliminó exitosamente
        
    Raises:
        ProjectNotFound: Si el proyecto no existe
        PermissionDenied: Si enforce_owner=True y el usuario no es propietario
    """
    def _work():
        project = _get_for_update(db, project_id)
        
        # BD 2.0 SSOT: comparar con auth_user_id
        if enforce_owner and project.auth_user_id != user_id:
            raise PermissionDenied(f"Usuario {user_id} no es propietario del proyecto {project_id}")
        
        # Registrar acción antes de eliminar
        audit.log_action(
            project_id=project.id,
            user_id=user_id,
            user_email=user_email,
            action=ProjectActionType.deleted,
            metadata={"name": project.project_name, "slug": project.project_slug}
        )
        
        # Eliminar proyecto
        db.delete(project)
        return True
    
    return commit_or_raise(db, _work)


def _get_for_update(db: Session, project_id: UUID) -> Project:
    """
    Obtiene un proyecto para actualización con bloqueo pesimista.
    
    Usa SELECT ... FOR UPDATE para prevenir condiciones de carrera.
    
    Args:
        db: Sesión SQLAlchemy
        project_id: ID del proyecto
        
    Returns:
        Instancia de Project
        
    Raises:
        ProjectNotFound: Si el proyecto no existe
    """
    project = db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    ).scalars().first()
    
    if not project:
        raise ProjectNotFound(project_id)
    return project


__all__ = [
    "create",
    "update",
    "delete",
    "ALLOWED_UPDATE_FIELDS",
]
