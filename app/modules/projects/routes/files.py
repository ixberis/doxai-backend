
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/files.py

Rutas de operaciones de archivos asociados a proyectos
(add, validate, move, delete) usando ProjectFileFacade.

Autor: Ixchel Beristain
Fecha: 02/11/2025
"""
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, Field

from app.modules.projects.services import ProjectsCommandService, ProjectsQueryService
from app.modules.projects.routes.deps import (
    get_projects_command_service,
    get_projects_query_service,
)

# SSOT: get_current_user_ctx (Core) para rutas optimizadas (~40ms vs ~1200ms ORM)
from app.modules.auth.services import get_current_user_ctx
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO

router = APIRouter()


# Helper local eliminado - usar extract_user_id_and_email de app.shared.auth_context

# ====== Schemas locales mínimos para inputs de archivo ======

class ProjectFileAddIn(BaseModel):
    path: str = Field(..., description="Ruta de almacenamiento (Storage)")
    filename: str = Field(..., description="Nombre del archivo")
    mime_type: Optional[str] = Field(None, description="MIME del archivo")
    size_bytes: Optional[int] = Field(None, ge=0, description="Tamaño en bytes")
    checksum: Optional[str] = Field(None, description="Hash del archivo")

class ProjectFileMoveIn(BaseModel):
    new_path: str = Field(..., description="Nueva ruta de almacenamiento")

# ====== Endpoints ======

@router.get(
    "/{project_id}/files",
    summary="Listar archivos del proyecto"
)
async def list_project_files(
    project_id: UUID,
    limit: int = 100,
    offset: int = 0,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """
    Lista archivos del proyecto. Siempre devuelve total.
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    items, total = await q.list_files(
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        limit=limit,
        offset=offset,
        include_total=True
    )
    return {
        "success": True,
        "items": items,
        "total": total
    }

@router.post(
    "/{project_id}/files",
    status_code=http_status.HTTP_201_CREATED,
    summary="Registrar archivo en proyecto (post-upload)"
)
async def add_project_file(
    project_id: UUID,
    payload: ProjectFileAddIn,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Agrega archivo al proyecto. Delega validación a service.
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    file = await svc.add_file(
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        user_email=None,  # BD 2.0: email no requerido
        path=payload.path,
        filename=payload.filename,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        checksum=payload.checksum
    )
    return {"success": True, "file_id": str(file.id)}

@router.post(
    "/files/{file_id}/validate",
    summary="Marcar archivo como validado"
)
async def validate_project_file(
    file_id: UUID,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Valida archivo. Delega lógica a service.
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    file = await svc.validate_file(
        file_id=file_id,
        auth_user_id=ctx.auth_user_id,
        user_email=None  # BD 2.0: email no requerido
    )
    return {"success": True, "file_id": str(file.id)}

@router.post(
    "/files/{file_id}/move",
    summary="Mover archivo a nueva ruta"
)
async def move_project_file(
    file_id: UUID,
    payload: ProjectFileMoveIn,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Mueve archivo. Delega lógica a service.
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    file = await svc.move_file(
        file_id=file_id,
        auth_user_id=ctx.auth_user_id,
        user_email=None,  # BD 2.0: email no requerido
        new_path=payload.new_path
    )
    return {"success": True, "file_id": str(file.id), "new_path": file.path}

@router.delete(
    "/files/{file_id}",
    summary="Eliminar archivo"
)
async def delete_project_file(
    file_id: UUID,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """
    Elimina archivo. Delega lógica a service.
    BD 2.0 SSOT: usa auth_user_id del contexto Core.
    """
    ok = await svc.delete_file(
        file_id=file_id,
        auth_user_id=ctx.auth_user_id,
        user_email=None  # BD 2.0: email no requerido
    )
    return {"success": bool(ok)}

# Fin del archivo backend/app/modules/projects/routes/files.py
