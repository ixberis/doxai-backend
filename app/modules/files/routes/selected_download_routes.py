# -*- coding: utf-8 -*-
"""
backend/app/modules/files/routes/selected_download_routes.py

Endpoint para descarga de archivos seleccionados como ZIP.

POST /files/{project_id}/download-selected
- Recibe lista de paths de storage
- Valida ownership del proyecto
- Genera ZIP con los archivos solicitados
- Retorna ZIP binario o error estructurado

Autor: DoxAI
Fecha: 2026-01-21
"""

from __future__ import annotations

import io
import logging
import zipfile
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.shared.config import settings
from app.modules.auth.services import get_current_user_ctx
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO
from app.modules.projects.models import Project

logger = logging.getLogger(__name__)

router = APIRouter(tags=["files:download"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SelectedDownloadRequest(BaseModel):
    """Request body para descarga de archivos seleccionados."""
    paths: List[str] = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="Lista de rutas de storage a descargar (máx 100)"
    )


class DownloadErrorResponse(BaseModel):
    """Respuesta de error para descarga."""
    error: str
    message: str
    missing_paths: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def validate_project_ownership(
    db: AsyncSession,
    project_id: UUID,
    auth_user_id: UUID,
) -> Project:
    """
    Valida que el proyecto existe y pertenece al usuario.
    
    Raises:
        HTTPException 404: Si el proyecto no existe
        HTTPException 403: Si el usuario no es dueño
    """
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto {project_id} no encontrado"
        )
    
    if project.auth_user_id != auth_user_id:
        logger.warning(
            "download_selected_forbidden project_id=%s user=%s owner=%s",
            project_id, auth_user_id, project.auth_user_id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este proyecto"
        )
    
    return project


def validate_path_ownership(
    path: str,
    auth_user_id: UUID,
    project_id: UUID,
) -> bool:
    """
    Valida que el path pertenece al usuario y proyecto.
    
    Expected format: users/{auth_user_id}/projects/{project_id}/...
    """
    expected_prefix = f"users/{auth_user_id}/projects/{project_id}/"
    return path.startswith(expected_prefix)


def is_system_file(path: str) -> bool:
    """
    Detecta archivos del sistema (dotfiles) que deben excluirse.
    """
    filename = path.split("/")[-1] if "/" in path else path
    return filename.startswith(".")


async def download_file_content(path: str, bucket: str) -> Optional[bytes]:
    """
    Descarga contenido de un archivo desde Supabase Storage.
    
    Returns:
        bytes si existe, None si no existe
    """
    from app.shared.utils.http_storage_client import get_http_storage_client
    
    try:
        client = get_http_storage_client()
        result = await client.download_file(bucket, path)
        
        if result.get("not_modified"):
            # Shouldn't happen without If-None-Match, but handle it
            return None
        
        return result.get("content")
    except FileNotFoundError:
        logger.debug("download_file_not_found path=%s", path)
        return None
    except Exception as e:
        logger.warning("download_file_error path=%s error=%s", path, str(e))
        return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/download-selected",
    summary="Descargar archivos seleccionados como ZIP",
    response_class=Response,
    responses={
        200: {
            "description": "ZIP con archivos solicitados",
            "content": {"application/zip": {}},
        },
        207: {
            "description": "ZIP parcial - algunos archivos no encontrados",
            "content": {"application/zip": {}},
        },
        400: {"description": "Request inválido"},
        403: {"description": "Sin acceso al proyecto"},
        404: {"description": "Proyecto no encontrado o todos los archivos faltantes"},
    },
)
async def download_selected_files(
    project_id: UUID,
    request: SelectedDownloadRequest,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
    db: AsyncSession = Depends(get_db),
):
    """
    Descarga archivos seleccionados como ZIP.
    
    - Valida ownership del proyecto
    - Filtra paths inválidos y archivos del sistema
    - Genera ZIP en memoria
    - Retorna 200 con ZIP si todos existen
    - Retorna 207 con ZIP parcial si algunos faltan (header X-Download-Missing-Count)
    - Retorna 404 si todos faltan
    """
    auth_user_id = UUID(ctx.auth_user_id)
    paths = request.paths
    
    logger.info(
        "download_selected_started project_id=%s user=%s paths_count=%d",
        project_id, auth_user_id, len(paths)
    )
    
    # Validar ownership del proyecto
    await validate_project_ownership(db, project_id, auth_user_id)
    
    # Filtrar paths
    valid_paths: List[str] = []
    invalid_paths: List[str] = []
    system_files: List[str] = []
    
    for path in paths:
        if is_system_file(path):
            system_files.append(path)
            continue
        
        if not validate_path_ownership(path, auth_user_id, project_id):
            logger.warning(
                "download_selected_invalid_path path=%s user=%s project=%s",
                path, auth_user_id, project_id
            )
            invalid_paths.append(path)
            continue
        
        valid_paths.append(path)
    
    if not valid_paths:
        logger.warning(
            "download_selected_no_valid_paths project_id=%s invalid=%d system=%d",
            project_id, len(invalid_paths), len(system_files)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "no_valid_paths",
                "message": "No hay archivos válidos para descargar",
                "invalid_count": len(invalid_paths),
                "system_files_count": len(system_files),
            }
        )
    
    # Descargar archivos y crear ZIP
    bucket = settings.supabase_bucket_name
    zip_buffer = io.BytesIO()
    
    downloaded_count = 0
    missing_paths: List[str] = []
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in valid_paths:
            content = await download_file_content(path, bucket)
            
            if content is None:
                missing_paths.append(path)
                continue
            
            # Usar solo el nombre del archivo en el ZIP (no la ruta completa)
            filename = path.split("/")[-1] if "/" in path else path
            
            # Si hay duplicados, añadir sufijo numérico
            existing_names = [info.filename for info in zf.filelist]
            if filename in existing_names:
                base, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
                counter = 1
                while f"{base}_{counter}.{ext}" in existing_names:
                    counter += 1
                filename = f"{base}_{counter}.{ext}" if ext else f"{base}_{counter}"
            
            zf.writestr(filename, content)
            downloaded_count += 1
    
    # Verificar resultado
    if downloaded_count == 0:
        logger.warning(
            "download_selected_all_missing project_id=%s missing_count=%d",
            project_id, len(missing_paths)
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "all_files_missing",
                "message": "Ninguno de los archivos solicitados fue encontrado",
                "missing_paths": missing_paths[:10],  # Limitar para no exponer demasiado
                "missing_count": len(missing_paths),
            }
        )
    
    zip_content = zip_buffer.getvalue()
    zip_size = len(zip_content)
    
    # Determinar status code
    if missing_paths:
        status_code = 207  # Partial Content
        logger.info(
            "download_selected_partial project_id=%s downloaded=%d missing=%d bytes=%d",
            project_id, downloaded_count, len(missing_paths), zip_size
        )
    else:
        status_code = 200
        logger.info(
            "download_selected_ok project_id=%s files=%d bytes=%d",
            project_id, downloaded_count, zip_size
        )
    
    # Headers de respuesta
    headers = {
        "Content-Disposition": f'attachment; filename="project-{project_id}-selected.zip"',
        "X-Download-Count": str(downloaded_count),
        "X-Download-Missing-Count": str(len(missing_paths)),
    }
    
    if missing_paths:
        # Incluir hasta 5 paths faltantes en header (para debug)
        headers["X-Download-Missing-Paths"] = ",".join(missing_paths[:5])
    
    return Response(
        content=zip_content,
        status_code=status_code,
        media_type="application/zip",
        headers=headers,
    )


# Fin del archivo backend/app/modules/files/routes/selected_download_routes.py
