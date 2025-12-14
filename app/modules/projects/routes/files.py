
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

# Dependencias
from app.modules.auth.services import get_current_user

router = APIRouter()

# --- Helper universal para user_id/email ---
from fastapi import HTTPException, status
def _uid_email(u):
    # acepta objeto o dict
    user_id = getattr(u, "user_id", None) or getattr(u, "id", None)
    email = getattr(u, "email", None)
    if user_id is None and isinstance(u, dict):
        user_id = u.get("user_id") or u.get("id")
        email = email or u.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth context")
    return user_id, email

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
def list_project_files(
    project_id: UUID,
    limit: int = 100,
    offset: int = 0,
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """Lista archivos del proyecto. Siempre devuelve total."""
    uid, _ = _uid_email(user)
    items, total = q.list_files(project_id=project_id, user_id=uid, limit=limit, offset=offset, include_total=True)
    # items son dicts, no necesitan conversión
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
def add_project_file(
    project_id: UUID,
    payload: ProjectFileAddIn,
    user=Depends(get_current_user),
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """Agrega archivo al proyecto. Delega validación a service."""
    uid, uemail = _uid_email(user)
    file = svc.add_file(
        project_id=project_id,
        user_id=uid,
        user_email=uemail,
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
def validate_project_file(
    file_id: UUID,
    user=Depends(get_current_user),
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """Valida archivo. Delega lógica a service."""
    uid, uemail = _uid_email(user)
    file = svc.validate_file(
        file_id=file_id,
        user_id=uid,
        user_email=uemail
    )
    return {"success": True, "file_id": str(file.id)}

@router.post(
    "/files/{file_id}/move",
    summary="Mover archivo a nueva ruta"
)
def move_project_file(
    file_id: UUID,
    payload: ProjectFileMoveIn,
    user=Depends(get_current_user),
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """Mueve archivo. Delega lógica a service."""
    uid, uemail = _uid_email(user)
    file = svc.move_file(
        file_id=file_id,
        user_id=uid,
        user_email=uemail,
        new_path=payload.new_path
    )
    return {"success": True, "file_id": str(file.id), "new_path": file.path}

@router.delete(
    "/files/{file_id}",
    summary="Eliminar archivo"
)
def delete_project_file(
    file_id: UUID,
    user=Depends(get_current_user),
    svc: ProjectsCommandService = Depends(get_projects_command_service),
):
    """Elimina archivo. Delega lógica a service."""
    uid, uemail = _uid_email(user)
    ok = svc.delete_file(
        file_id=file_id,
        user_id=uid,
        user_email=uemail
    )
    return {"success": bool(ok)}

# Fin del archivo backend/app/modules/projects/routes/files.py
