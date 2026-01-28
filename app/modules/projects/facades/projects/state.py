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

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus
from app.modules.projects.enums.project_action_type_enum import ProjectActionType
from app.modules.projects.enums.project_state_transitions import validate_state_transition
from app.modules.projects.facades.errors import (
    ProjectNotFound, 
    InvalidStateTransition, 
    PermissionDenied, 
    ProjectCloseNotAllowed,
    ProjectHardDeleteNotAllowed,
    ProjectHardDeleteAuditFailed,
)
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

async def close_project(
    db: AsyncSession,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,
    user_email: str,
    enforce_owner: bool = True,
    closed_reason: str = "user_closed_from_dashboard"
) -> Project:
    """
    Cierra un proyecto (inicia ciclo de retención).
    
    Opción B: Permite cerrar desde casi cualquier project_state.
    
    Estados permitidos:
    - created, uploading, ready, error, archived → OK, se cierra
    - processing → RECHAZADO (evitar cortar proceso activo)
    
    Efectos:
    - status cambia a 'closed'
    - closed_at se fija automáticamente (trigger DB)
    - Se registra en project_action_logs con action_details='project_closed'
    
    Idempotencia:
    - Si ya está closed/retention_grace/deleted_by_policy → return OK sin cambios
    
    Raises:
        PermissionDenied: si el usuario no es propietario
        ProjectCloseNotAllowed: si el proyecto está en state='processing'
    
    Args:
        closed_reason: Razón del cierre para auditoría (default: 'user_closed_from_dashboard')
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    """
    async def _work() -> Project:
        project = await _get_for_update(db, project_id)
        
        # BD 2.0 SSOT: comparar con auth_user_id
        if enforce_owner and project.auth_user_id != user_id:
            raise PermissionDenied(f"Usuario {user_id} no es propietario del proyecto {project_id}")
        
        # Opción B: Bloquear SOLO si está en processing
        if project.state == ProjectState.processing:
            raise ProjectCloseNotAllowed(
                current_state=project.state.value,
                reason="No puedes cerrar un proyecto mientras está procesando. Intenta de nuevo cuando termine."
            )
        
        # Ya cerrado / retention_grace / deleted_by_policy? → idempotencia
        closed_statuses = {ProjectStatus.CLOSED, ProjectStatus.RETENTION_GRACE, ProjectStatus.DELETED_BY_POLICY}
        if project.status in closed_statuses:
            audit.log_action(
                project_id=project.id,
                auth_user_id=user_id,
                action_type=ProjectActionType.updated,
                action_details="project_closed",
                action_metadata={
                    "field": "status",
                    "from": project.status.value,
                    "to": project.status.value,
                    "note": "no-op (proyecto ya estaba cerrado o en retención)",
                    "from_state": project.state.value,
                    "closed_reason": closed_reason,
                }
            )
            return project
        
        # Guardar estados anteriores para auditoría
        old_status = project.status
        old_state = project.state
        
        # Cambiar status a closed (NO tocamos project.state)
        project.status = ProjectStatus.CLOSED
        
        audit.log_action(
            project_id=project.id,
            auth_user_id=user_id,
            action_type=ProjectActionType.updated,
            action_details="project_closed",
            action_metadata={
                "field": "status",
                "from_status": old_status.value,
                "to_status": "closed",
                "from_state": old_state.value,
                "ready_at": project.ready_at.isoformat() if project.ready_at else None,
                "retention_started": True,
                "closed_reason": closed_reason,
            }
        )
        
        return project
    
    return await commit_or_raise(db, _work)


async def hard_delete_closed_project(
    db: AsyncSession,
    audit: AuditLogger,
    project_id: UUID,
    *,
    user_id: UUID,
    enforce_owner: bool = True
) -> bool:
    """
    Elimina completamente un proyecto cerrado (hard delete).
    
    RFC-FILES-RETENTION-001: Solo disponible para proyectos cerrados.
    
    Requisitos:
    - El proyecto debe tener status !== 'in_process'
    - El usuario debe ser propietario
    
    Efectos:
    - ANTES de borrar: inserta evento en project_deletion_audit_events
    - El proyecto desaparece del historial (logs con FK se borran por CASCADE)
    - No afecta métricas agregadas ni billing histórico
    
    Auditoría persistente:
    - Se inserta fila en project_deletion_audit_events ANTES del delete
    - Si falla el INSERT de auditoría, se aborta el delete (fail-fast)
    
    BD 2.0 SSOT: user_id param se compara con auth_user_id column.
    
    Raises:
        ProjectHardDeleteNotAllowed: si el proyecto está activo (in_process)
        ProjectHardDeleteAuditFailed: si falla el INSERT de auditoría
        PermissionDenied: si el usuario no es propietario
    """
    import logging
    from sqlalchemy import text
    
    logger = logging.getLogger(__name__)
    
    async def _work() -> bool:
        project = await _get_for_update(db, project_id)
        
        # BD 2.0 SSOT: comparar con auth_user_id
        if enforce_owner and project.auth_user_id != user_id:
            raise PermissionDenied(f"Usuario {user_id} no es propietario del proyecto {project_id}")
        
        # Solo proyectos cerrados pueden eliminarse definitivamente
        if project.status == ProjectStatus.IN_PROCESS:
            raise ProjectHardDeleteNotAllowed(
                reason="No se puede eliminar un proyecto activo. Primero debe cerrarlo."
            )
        
        # =====================================================================
        # AUDITORÍA PERSISTENTE: Insertar ANTES del delete via SECURITY DEFINER
        # Si falla, NO ejecutamos el delete (fail-fast)
        # =====================================================================
        try:
            # Usar función SECURITY DEFINER para bypass de RLS
            audit_fn = text("""
                SELECT public.fn_insert_project_deletion_audit_event(
                    :project_id::uuid,
                    :auth_user_id::uuid,
                    :project_slug,
                    :project_name,
                    :project_status,
                    :project_state,
                    'project_hard_delete'
                )
            """)
            await db.execute(audit_fn, {
                "project_id": str(project.id),
                "auth_user_id": str(user_id),
                "project_slug": project.project_slug,
                "project_name": project.project_name,
                "project_status": project.status.value,
                "project_state": project.state.value,
            })
        except Exception as e:
            # =========================================================================
            # LOGGING EXPLÍCITO: Capturar SQLSTATE + mensaje + tipo de excepción
            # IMPORTANTE: Incluir toda la info para debug sin depender de Railway logs
            # =========================================================================
            import sys
            
            # Extraer SQLSTATE (asyncpg: e.sqlstate, psycopg2: e.orig.pgcode)
            sqlstate = getattr(e, 'sqlstate', None) or getattr(getattr(e, 'orig', None), 'pgcode', None)
            db_message = str(e)
            exception_type = type(e).__module__ + "." + type(e).__name__
            
            # stderr con flush=True para Railway
            print(
                f"ERROR project_hard_delete_audit_failed "
                f"project_id={project.id} "
                f"auth_user_id={user_id} "
                f"sqlstate={sqlstate} "
                f"exception_type={exception_type} "
                f"db_message={db_message}",
                file=sys.stderr,
                flush=True,
            )
            
            # logger.error inline (sin extra={}) para consistencia
            logger.error(
                f"project_hard_delete_audit_failed "
                f"project_id={project.id} "
                f"auth_user_id={user_id} "
                f"sqlstate={sqlstate} "
                f"exception_type={exception_type} "
                f"db_message={db_message}"
            )
            
            raise ProjectHardDeleteAuditFailed(
                project_id, 
                f"sqlstate={sqlstate} {db_message}",
                sqlstate=sqlstate,
                db_message=db_message,
                exception_type=exception_type,
            )
        
        # Log via app logger (redundancia, la auditoría persistente es la SSOT)
        logger.info(
            "project_hard_deleted",
            extra={
                "project_id": str(project.id),
                "auth_user_id": str(user_id),
                "status": project.status.value,
                "state": project.state.value,
                "project_name": project.project_name,
            }
        )
        
        # Hard delete via SQL DELETE (evita cargar relaciones ORM inexistentes)
        # Los logs se borran por FK ON DELETE CASCADE (DB-level)
        result = await db.execute(
            sa.delete(Project).where(Project.id == project_id)
        )
        
        # Verificar que se borró exactamente 1 fila
        if result.rowcount != 1:
            raise ProjectNotFound(project_id)
        
        return True
    
    return await commit_or_raise(db, _work)


__all__ = [
    "change_status",
    "transition_state",
    "archive",
    "close_project",
    "hard_delete_closed_project",
]
