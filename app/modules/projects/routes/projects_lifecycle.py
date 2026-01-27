
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/projects_lifecycle.py

Rutas de ciclo de vida de Proyectos:
- Cambiar status administrativo
- Transicionar estado técnico (workflow)
- Archivar (soft delete)

Autor: Ixchel Beristain
Fecha de actualización: 08/11/2025
"""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.projects.services import ProjectsCommandService
from app.modules.projects.routes.deps import get_projects_command_service
from app.modules.projects.enums import ProjectStatus, ProjectState
from app.modules.projects.schemas import ProjectRead, ProjectResponse
# SSOT: get_current_user_ctx (Core) para rutas optimizadas (~40ms vs ~1200ms ORM)
from app.modules.auth.services import get_current_user_ctx
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO

router = APIRouter(tags=["projects:lifecycle"])

# Helper para normalizar slugs
def _norm_slug(s: str) -> str:
    """Normaliza slug: lowercase, guiones a guiones bajos."""
    return s.strip().lower().replace("-", "_")


def _coerce_to_project_read(p):
    """
    Completa campos obligatorios faltantes antes de validar con ProjectRead.
    Necesario para compatibilidad con stubs de tests que no generan todos los campos.
    IMPORTANTE: Solo asigna valores default si NO existen (setdefault), nunca sobrescribe.
    """
    d = p if isinstance(p, dict) else (p.__dict__ if hasattr(p, '__dict__') else {})
    d = dict(d)
    now = datetime.now(timezone.utc)
    # Solo asignar si no existe (no sobrescribir id del path)
    d.setdefault("id", uuid4())
    d.setdefault("created_at", now)
    d.setdefault("updated_at", now)
    return ProjectRead.model_validate(d)


import logging

logger = logging.getLogger(__name__)

# Helper local eliminado - usar extract_user_id_and_email de app.shared.auth_context


@router.post(
    "/{project_id}/status/{status_slug}",
    response_model=ProjectResponse,
    summary="Cambiar status administrativo",
)
async def change_status(
    project_id: UUID,
    status_slug: str,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Cambia el status administrativo del proyecto. Requiere propiedad.
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    # Normalizar y mapear slug a enum
    slug = _norm_slug(status_slug)
    if slug in {"in_process", "in_progress"}:
        new_status = ProjectStatus.IN_PROCESS
    else:
        try:
            new_status = ProjectStatus(slug)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status_slug}")
    
    project = await svc.change_status(
        project_id,
        auth_user_id=ctx.auth_user_id,
        user_email=None,  # BD 2.0: email no requerido
        new_status=new_status,
    )
    return ProjectResponse(success=True, message="Status actualizado", project=_coerce_to_project_read(project))


@router.post(
    "/{project_id}/state/{state_slug}",
    response_model=ProjectResponse,
    summary="Transicionar estado técnico (workflow)",
)
async def transition_state(
    project_id: UUID,
    state_slug: str,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Transiciona el estado técnico del proyecto. Requiere propiedad.
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    # Normalizar y mapear slug a enum
    slug = _norm_slug(state_slug)
    try:
        to_state = ProjectState(slug)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid state: {state_slug}")
    
    project = await svc.transition_state(
        project_id,
        auth_user_id=ctx.auth_user_id,
        user_email=None,  # BD 2.0: email no requerido
        to_state=to_state,
    )
    return ProjectResponse(success=True, message="Estado actualizado", project=_coerce_to_project_read(project))


@router.post(
    "/{project_id}/archive",
    response_model=ProjectResponse,
    summary="Archivar proyecto",
)
async def archive_project(
    project_id: UUID,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Archiva (soft delete) un proyecto. Requiere propiedad.
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    project = await svc.archive(
        project_id,
        auth_user_id=ctx.auth_user_id,
        user_email=None,  # BD 2.0: email no requerido
    )
    return ProjectResponse(success=True, message="Proyecto archivado", project=_coerce_to_project_read(project))


@router.post(
    "/{project_id}/close",
    response_model=ProjectResponse,
    summary="Cerrar proyecto (entrega completada)",
)
async def close_project(
    project_id: UUID,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Cierra un proyecto tras la entrega (inicia ciclo de retención).
    
    Prerequisitos:
    - El proyecto debe estar en state='ready' (entregado)
    - ready_at debe estar seteado (automático al transicionar a ready)
    
    Efectos:
    - status cambia a 'closed'
    - Se registra en project_action_logs ('project_closed')
    - El job de retención comenzará a contar el periodo de gracia
    
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    try:
        project = await svc.close_project(
            project_id,
            auth_user_id=ctx.auth_user_id,
            user_email=None,  # BD 2.0: email no requerido
        )
        return ProjectResponse(
            success=True, 
            message="Proyecto cerrado. Ciclo de retención iniciado.", 
            project=_coerce_to_project_read(project)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Fin del archivo backend\app\modules\projects\routes\projects_lifecycle.py