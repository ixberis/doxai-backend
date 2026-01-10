
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/projects_crud.py

Rutas CRUD de Proyectos:
- Crear
- Obtener por ID / por slug
- Actualizar metadatos (nombre/descripcion)
- Eliminar (hard delete)

Autor: Ixchel Beristain
Fecha de actualización: 08/11/2025
"""
from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.modules.projects.services import ProjectsCommandService, ProjectsQueryService
from app.modules.projects.routes.deps import (
    get_projects_command_service,
    get_projects_query_service,
)
from app.modules.projects.schemas import (
    ProjectCreateIn,
    ProjectUpdateIn,
    ProjectRead,
    ProjectResponse,
)
from app.modules.auth.services import get_current_user
from app.shared.auth_context import extract_user_id_and_email

router = APIRouter(tags=["projects:crud"])


def _coerce_to_project_read(p):
    """
    Convierte un Project (ORM) o dict a ProjectRead.
    Para modelos ORM usa from_attributes=True de Pydantic.
    Para dicts (stubs de tests) completa campos faltantes.
    """
    from app.modules.projects.models.project_models import Project as ProjectModel
    
    # Si es un modelo ORM, usar model_validate directamente (from_attributes=True)
    if isinstance(p, ProjectModel):
        return ProjectRead.model_validate(p)
    
    # Para dicts (stubs de tests), completar campos faltantes
    d = dict(p) if isinstance(p, dict) else {}
    now = datetime.now(timezone.utc)
    d.setdefault("id", uuid4())
    d.setdefault("created_at", now)
    d.setdefault("updated_at", now)
    return ProjectRead.model_validate(d)


import logging

logger = logging.getLogger(__name__)

# Helper local eliminado - usar extract_user_id_and_email de app.shared.auth_context


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear proyecto",
)
async def create_project(
    payload: ProjectCreateIn,
    user=Depends(get_current_user),
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Crea un proyecto nuevo para el usuario autenticado.
    """
    uid, uemail = extract_user_id_and_email(user)
    project = await svc.create_project(
        user_id=uid,
        user_email=uemail,
        project_name=payload.project_name,
        project_slug=payload.project_slug,
        project_description=payload.project_description,
    )
    return ProjectResponse(success=True, message="Proyecto creado", project=_coerce_to_project_read(project))


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Obtener proyecto por ID",
)
async def get_project_by_id(
    project_id: UUID,
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """
    Devuelve un proyecto por su ID, validando pertenencia del usuario.
    BD 2.0 SSOT: ownership se valida contra auth_user_id (UUID).
    """
    uid, _ = extract_user_id_and_email(user)
    project = await q.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")

    # BD 2.0 SSOT: comparar con auth_user_id (UUID)
    project_owner = project.get("auth_user_id") if isinstance(project, dict) else getattr(project, "auth_user_id", None)
    # Normalizar a string para comparación (puede venir como UUID o str)
    if str(project_owner) != str(uid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")

    return _coerce_to_project_read(project)



@router.get(
    "/slug/{slug}",
    response_model=ProjectRead,
    summary="Obtener proyecto por slug",
)
def get_project_by_slug(
    slug: str,
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """
    Devuelve un proyecto por su slug, validando pertenencia del usuario.
    BD 2.0 SSOT: ownership se valida contra auth_user_id (UUID).
    """
    uid, _ = extract_user_id_and_email(user)
    project = q.get_project_by_slug(slug)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")

    # BD 2.0 SSOT: comparar con auth_user_id (UUID)
    project_owner = project.get("auth_user_id") if isinstance(project, dict) else getattr(project, "auth_user_id", None)
    # Normalizar a string para comparación (puede venir como UUID o str)
    if str(project_owner) != str(uid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado")

    return _coerce_to_project_read(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Actualizar metadatos (nombre, descripción)",
)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdateIn,
    user=Depends(get_current_user),
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Actualiza metadatos del proyecto (nombre/ descripción). Requiere propiedad.
    """
    uid, uemail = extract_user_id_and_email(user)
    project = await svc.update_project(
        project_id,
        user_id=uid,
        user_email=uemail,
        **payload.model_dump(exclude_none=True),
    )
    return ProjectResponse(success=True, message="Proyecto actualizado", project=_coerce_to_project_read(project))


@router.delete(
    "/{project_id}",
    response_model=dict,
    summary="Eliminar proyecto (hard delete; uso administrativo)",
)
async def delete_project(
    project_id: UUID,
    user=Depends(get_current_user),
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Elimina físicamente un proyecto. Normalmente reservado a tareas administrativas.
    """
    uid, uemail = extract_user_id_and_email(user)
    ok = await svc.delete(
        project_id,
        user_id=uid,
        user_email=uemail,
    )
    return {"success": bool(ok), "message": "Proyecto eliminado" if ok else "No se pudo eliminar"}

# Fin del archivo backend\app\modules\projects\routes\projects_crud.py