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

import asyncio
import io
import logging
import time
import zipfile
from typing import List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.shared.config import settings
from app.shared.utils.storage_errors import StorageRequestError
from app.modules.auth.services import get_current_user_ctx
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO
from app.modules.projects.models import Project
from app.shared.observability.timed_route import TimedAPIRoute

logger = logging.getLogger(__name__)

# Límite de concurrencia para descargas paralelas
DOWNLOAD_CONCURRENCY_LIMIT = 6

router = APIRouter(tags=["files:download"], route_class=TimedAPIRoute)


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


async def download_file_content(path: str, bucket: str) -> Tuple[Optional[bytes], Optional[StorageRequestError]]:
    """
    Descarga contenido de un archivo desde Supabase Storage.
    
    Returns:
        Tuple[bytes | None, StorageRequestError | None]:
        - (bytes, None) si existe
        - (None, None) si no existe (404 o 400 con body "not found")
        - (None, StorageRequestError) si hay error de storage (400/401/403/5xx genuino)
    """
    from app.shared.utils.http_storage_client import get_http_storage_client
    
    try:
        client = get_http_storage_client()
        result = await client.download_file(bucket, path, try_signed_fallback=True)
        
        if result.get("not_modified"):
            return None, None
        
        return result.get("content"), None
    except FileNotFoundError:
        logger.debug("download_file_not_found path=%s", path)
        return None, None
    except StorageRequestError as e:
        # Log con detalles completos para diagnóstico
        logger.warning(
            "download_selected_storage_error status=%d bucket=%s path=%s url=%s body=%s",
            e.status_code, 
            e.bucket, 
            e.path,
            e.url.split("?")[0] if e.url else "unknown",
            e.body_snippet[:200] if e.body_snippet else "empty"
        )
        return None, e
    except Exception as e:
        logger.warning("download_file_unexpected_error path=%s error=%s type=%s", path, str(e), type(e).__name__)
        return None, None


async def download_files_parallel(
    paths: List[str],
    bucket: str,
    concurrency_limit: int = DOWNLOAD_CONCURRENCY_LIMIT,
) -> Tuple[List[Tuple[str, Optional[bytes]]], List[str], Optional[StorageRequestError], float]:
    """
    Descarga múltiples archivos en paralelo con límite de concurrencia.
    
    Args:
        paths: Lista de rutas a descargar
        bucket: Nombre del bucket
        concurrency_limit: Máximo de descargas simultáneas
    
    Returns:
        Tuple de:
        - Lista de (path, content|None) para archivos procesados
        - Lista de paths faltantes (404)
        - StorageRequestError si hubo error crítico (None si no)
        - Tiempo total de fetch en ms
    """
    semaphore = asyncio.Semaphore(concurrency_limit)
    results: List[Tuple[str, Optional[bytes]]] = []
    missing_paths: List[str] = []
    critical_error: Optional[StorageRequestError] = None
    
    async def download_with_semaphore(path: str) -> Tuple[str, Optional[bytes], Optional[StorageRequestError]]:
        async with semaphore:
            content, error = await download_file_content(path, bucket)
            return (path, content, error)
    
    start_time = time.perf_counter()
    
    # Ejecutar todas las descargas en paralelo (respetando el semáforo)
    tasks = [download_with_semaphore(path) for path in paths]
    download_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    fetch_ms = (time.perf_counter() - start_time) * 1000
    
    # Procesar resultados manteniendo orden determinista
    for i, result in enumerate(download_results):
        path = paths[i]
        
        if isinstance(result, Exception):
            logger.warning("download_parallel_exception path=%s error=%s", path, str(result))
            missing_paths.append(path)
            continue
        
        r_path, content, error = result
        
        # Si hay error de storage crítico (400/401/403/5xx), abort
        if error is not None:
            critical_error = error
            break
        
        if content is None:
            missing_paths.append(path)
        else:
            results.append((path, content))
    
    return results, missing_paths, critical_error, fetch_ms


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/download-selected",
    summary="Descargar archivos seleccionados como ZIP",
    response_class=Response,
    responses={
        200: {
            "description": "Archivo descargado o ZIP con archivos solicitados",
            "content": {"application/zip": {}, "application/octet-stream": {}},
        },
        207: {
            "description": "ZIP parcial - algunos archivos no encontrados",
            "content": {"application/zip": {}},
        },
        400: {"description": "Request inválido"},
        403: {"description": "Sin acceso al proyecto"},
        404: {"description": "Proyecto no encontrado o archivo no encontrado"},
        502: {"description": "Error de storage backend"},
    },
)
async def download_selected_files(
    project_id: UUID,
    request: SelectedDownloadRequest,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
    db: AsyncSession = Depends(get_db),
):
    """
    Descarga archivos seleccionados.
    
    - Si hay 1 archivo: descarga directa (no ZIP)
    - Si hay 2+: genera ZIP
    - Valida ownership del proyecto
    - Filtra paths inválidos y archivos del sistema
    - Retorna 200 si todos existen
    - Retorna 207 con ZIP parcial si algunos faltan (solo para multi-file, header X-Download-Missing-Count)
    - Retorna 404 si todos faltan o si el único archivo solicitado no existe
    - Retorna 502 si hay error de storage (400/401/403/5xx desde Supabase)
    """
    # Robust UUID normalization - handles both str and UUID objects
    raw_auth_user_id = ctx.auth_user_id
    if isinstance(raw_auth_user_id, UUID):
        auth_user_id = raw_auth_user_id
    else:
        auth_user_id = UUID(str(raw_auth_user_id))
    
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
    
    bucket = settings.supabase_bucket_name
    
    # --- SINGLE FILE: descarga directa (no ZIP) ---
    if len(valid_paths) == 1:
        single_path = valid_paths[0]
        content, storage_error = await download_file_content(single_path, bucket)
        
        # Si hay error de storage (400/401/403/5xx) -> 502
        if storage_error is not None:
            logger.warning(
                "download_selected_single_storage_error project_id=%s path=%s status=%d",
                project_id, single_path, storage_error.status_code
            )
            return JSONResponse(
                status_code=502,
                content=storage_error.to_dict(),
            )
        
        # Si no existe -> 404
        if content is None:
            logger.warning(
                "download_selected_single_missing project_id=%s path=%s",
                project_id, single_path
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "file_missing",
                    "message": "El archivo solicitado no fue encontrado",
                    "path": single_path,
                }
            )
        
        filename = single_path.split("/")[-1] if "/" in single_path else single_path
        
        # Detect content type from extension
        content_type = _guess_content_type(filename)
        
        logger.info(
            "download_selected_single_ok project_id=%s file=%s bytes=%d",
            project_id, filename, len(content)
        )
        
        return Response(
            content=content,
            status_code=200,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Download-Count": "1",
                "X-Download-Missing-Count": "0",
            },
        )
    
    # --- MULTIPLE FILES: descarga paralela + generar ZIP ---
    total_start = time.perf_counter()
    
    # Fase 1: Descargar archivos en paralelo
    downloaded_files, missing_paths, critical_error, fetch_ms = await download_files_parallel(
        valid_paths, bucket, DOWNLOAD_CONCURRENCY_LIMIT
    )
    
    # Si hay error de storage crítico (400/401/403/5xx) -> 502
    if critical_error is not None:
        logger.warning(
            "download_selected_multi_storage_error project_id=%s status=%d fetch_ms=%.2f",
            project_id, critical_error.status_code, fetch_ms
        )
        return JSONResponse(
            status_code=502,
            content=critical_error.to_dict(),
        )
    
    # Fase 2: Generar ZIP
    zip_start = time.perf_counter()
    zip_buffer = io.BytesIO()
    downloaded_count = 0
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        existing_names: List[str] = []
        
        for path, content in downloaded_files:
            if content is None:
                continue
            
            # Usar solo el nombre del archivo en el ZIP (no la ruta completa)
            filename = path.split("/")[-1] if "/" in path else path
            
            # Si hay duplicados, añadir sufijo numérico
            if filename in existing_names:
                base, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
                counter = 1
                while f"{base}_{counter}.{ext}" in existing_names:
                    counter += 1
                filename = f"{base}_{counter}.{ext}" if ext else f"{base}_{counter}"
            
            existing_names.append(filename)
            zf.writestr(filename, content)
            downloaded_count += 1
    
    zip_ms = (time.perf_counter() - zip_start) * 1000
    
    # Verificar resultado
    if downloaded_count == 0:
        logger.warning(
            "download_selected_all_missing project_id=%s missing_count=%d fetch_ms=%.2f",
            project_id, len(missing_paths), fetch_ms
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
    
    # Fase 3: Construir respuesta
    response_start = time.perf_counter()
    zip_content = zip_buffer.getvalue()
    zip_size = len(zip_content)
    
    # Headers de respuesta
    headers = {
        "Content-Disposition": f'attachment; filename="project-{project_id}-selected.zip"',
        "X-Download-Count": str(downloaded_count),
        "X-Download-Missing-Count": str(len(missing_paths)),
    }
    
    if missing_paths:
        # Incluir hasta 5 paths faltantes en header (para debug)
        headers["X-Download-Missing-Paths"] = ",".join(missing_paths[:5])
    
    response_obj = Response(
        content=zip_content,
        status_code=207 if missing_paths else 200,
        media_type="application/zip",
        headers=headers,
    )
    
    response_ms = (time.perf_counter() - response_start) * 1000
    total_ms = (time.perf_counter() - total_start) * 1000
    
    # Log con breakdown de fases
    if missing_paths:
        logger.info(
            "download_selected_partial project_id=%s downloaded=%d missing=%d bytes=%d "
            "fetch_ms=%.2f zip_ms=%.2f response_ms=%.2f total_ms=%.2f",
            project_id, downloaded_count, len(missing_paths), zip_size,
            fetch_ms, zip_ms, response_ms, total_ms
        )
    else:
        logger.info(
            "download_selected_ok project_id=%s files=%d bytes=%d "
            "fetch_ms=%.2f zip_ms=%.2f response_ms=%.2f total_ms=%.2f",
            project_id, downloaded_count, zip_size,
            fetch_ms, zip_ms, response_ms, total_ms
        )
    
    return response_obj


def _guess_content_type(filename: str) -> str:
    """
    Determina el Content-Type basado en la extensión del archivo.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    content_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "ppt": "application/vnd.ms-powerpoint",
        "txt": "text/plain",
        "csv": "text/csv",
        "odt": "application/vnd.oasis.opendocument.text",
        "ods": "application/vnd.oasis.opendocument.spreadsheet",
        "odp": "application/vnd.oasis.opendocument.presentation",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "json": "application/json",
        "xml": "application/xml",
    }
    
    return content_types.get(ext, "application/octet-stream")


# Fin del archivo backend/app/modules/files/routes/selected_download_routes.py
