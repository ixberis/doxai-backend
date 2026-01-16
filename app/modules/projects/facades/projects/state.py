# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/projects/state.py

Operaciones de cambio de estado: status, state transitions, archive.
Incluye validación de transiciones y seteo de timestamps especiales.

BD 2.0 SSOT:
- auth_user_id: UUID canónico de ownership (reemplaza user_id legacy)

Transacciones: Usa commit_or_raise como única fuente de verdad.
Runtime: AsyncSession only (producción).

Autor: Ixchel Beristain
Fecha: 2025-10-26
Actualizado: 2026-01-16 - Async-only, tx unificado en commit_or_raise
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_state_transitions import validate_state_transition
from app.modules.projects.facades.errors import ProjectNotFound, InvalidStateTransition, PermissionDenied
from app.modules.projects.facades.base import now_utc, commit_or_raise
from app.modules.projects.facades.audit_logger import AuditLogger


async def _get_for_update(db: AsyncSession, project_id: UUID) -> Project:
    """Obtiene un proyecto para actualización con bloqueo pesimista."""
    result = await db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    project = result.scalars().first()
    
    if not project:
        raise ProjectNotFound(project_id)
    return project


async def change_status(
    db: AsyncSession,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,
    user_email: str,
    new_status: ProjectStatus,
    enforce_owner: bool = True
) -> Project:
    """
    Cambia el status administrativo del proyecto.
    
    Status (administrativo/negocio) es independiente de state (técnico).
    No valida transiciones; es una propiedad de negocio libre.
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    Transacciones: commit_or_raise maneja commit/rollback.
    """
    async def _work() -> Project:
        project = await _get_for_update(db, project_id)
        
        # BD 2.0 SSOT: comparar con auth_user_id
        if enforce_owner and project.auth_user_id != user_id:
            raise PermissionDenied(f"Usuario {user_id} no es propietario del proyecto {project_id}")
        
        old_status = project.status
        project.status = new_status
        
        audit.log_action(
            project_id=project.id,
            auth_user_id=user_id,
            action_type=ProjectActionType.updated,
            action_metadata={
                "field": "status",
                "from": old_status.value,
                "to": new_status.value
            }
        )
        
        return project
    
    return await commit_or_raise(db, _work)


async def transition_state(
    db: AsyncSession,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,
    user_email: str,
    to_state: ProjectState,
    enforce_owner: bool = True
) -> Project:
    """
    Transiciona el estado técnico del proyecto.
    
    Reglas de dominio:
    1. Valida transición usando VALID_STATE_TRANSITIONS
    2. Idempotencia: si from_state == to_state, es no-op con log informativo
    3. Setea ready_at cuando to_state == ready
    4. Setea archived_at cuando to_state == archived
    5. Registra la transición en auditoría
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    Transacciones: commit_or_raise maneja commit/rollback (incluso para no-op).
    """
    async def _work() -> Project:
        project = await _get_for_update(db, project_id)
        
        # BD 2.0 SSOT: comparar con auth_user_id
        if enforce_owner and project.auth_user_id != user_id:
            raise PermissionDenied(f"Usuario {user_id} no es propietario del proyecto {project_id}")
        
        from_state = project.state
        
        # Idempotencia: si ya está en el estado destino, es no-op
        if from_state == to_state:
            audit.log_action(
                project_id=project.id,
                auth_user_id=user_id,
                action_type=ProjectActionType.updated,
                action_metadata={
                    "field": "state",
                    "from": from_state.value,
                    "to": to_state.value,
                    "note": "no-op (estado ya era el destino)"
                }
            )
            # commit_or_raise liberará el lock
            return project
        
        # Validar transición (lanza ValueError si es inválida)
        try:
            validate_state_transition(from_state, to_state)
        except ValueError as e:
            raise InvalidStateTransition(from_state, to_state, str(e))
        
        # Aplicar nueva state
        project.state = to_state
        
        # Timestamps de dominio: setear solo cuando corresponde
        if to_state == ProjectState.ready:
            project.ready_at = now_utc()
        
        if to_state == ProjectState.archived:
            project.archived_at = now_utc()
        
        # Registrar transición
        audit.log_action(
            project_id=project.id,
            auth_user_id=user_id,
            action_type=ProjectActionType.updated,
            action_metadata={
                "field": "state",
                "from": from_state.value,
                "to": to_state.value
            }
        )
        
        return project
    
    return await commit_or_raise(db, _work)


async def archive(
    db: AsyncSession,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,
    user_email: str,
    enforce_owner: bool = True
) -> Project:
    """
    Archiva un proyecto (soft delete).
    
    Wrapper sobre transition_state que mueve el proyecto a state=archived.
    Recomendado para eliminación de cara al usuario.
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    """
    return await transition_state(
        db=db,
        audit=audit,
        project_id=project_id,
        user_id=user_id,
        user_email=user_email,
        to_state=ProjectState.archived,
        enforce_owner=enforce_owner
    )


__all__ = [
    "change_status",
    "transition_state",
    "archive",
]
