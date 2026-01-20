# -*- coding: utf-8 -*-
"""
backend/app/modules/files/routes/project_file_activity_routes.py

Rutas de actividad de archivos bajo proyectos.
Contrato SSOT con frontend: /api/projects/{project_id}/file-activity/*

SSOT: persiste en public.product_file_activity vía product_file_activity_repository.

Incluye 17 endpoints:
- Input Files (10): upload, download, delete, restore, rename, replace, bulk/*
- Output Files (4): output/generated, output/downloaded, output/bulk/*
- Processing (3): processing/started, processing/completed, processing/failed

Autenticación: get_current_user_ctx (UUID SSOT)
Validación: ownership del proyecto

Autor: DoxAI Team
Fecha: 2026-01-19
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.services import get_current_user_ctx
from app.modules.auth.schemas import AuthContextDTO
from app.modules.projects.models.project_models import Project
from app.modules.files.enums import ProductFileEvent
from app.modules.files.repositories import product_file_activity_repository as activity_repo

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/projects/{project_id}/file-activity",
    tags=["projects:file-activity"],
)


# ---------------------------------------------------------------------------
# Mapping: Frontend file_event strings ↔ Backend ProductFileEvent
# ---------------------------------------------------------------------------

# Mapeo de endpoint/action → file_event string (para frontend)
ENDPOINT_TO_FILE_EVENT: dict[str, str] = {
    "upload": "input_file_uploaded",
    "download": "input_file_downloaded",
    "delete": "input_file_deleted",
    "restore": "input_file_restored",
    "rename": "input_file_renamed",
    "replace": "input_file_replaced",
    "bulk_upload": "input_files_bulk_uploaded",
    "bulk_delete": "input_files_bulk_deleted",
    "bulk_download": "input_files_bulk_downloaded",
    "output_generated": "output_file_generated",
    "output_downloaded": "output_file_downloaded",
    "output_bulk_generated": "output_files_bulk_generated",
    "output_bulk_downloaded": "output_files_bulk_downloaded",
    "processing_started": "project_processing_started",
    "processing_completed": "project_processing_completed",
    "processing_failed": "project_processing_failed",
}

# Mapeo de ProductFileEvent → file_event fallback (si no hay details.file_event)
EVENT_TYPE_TO_FILE_EVENT: dict[str, str] = {
    "uploaded": "input_file_uploaded",
    "downloaded": "input_file_downloaded",
    "deleted": "input_file_deleted",
    "updated": "input_file_restored",  # fallback genérico
    "generated": "output_file_generated",
    "processing": "project_processing_started",
    "completed": "project_processing_completed",
    "failed": "project_processing_failed",
}


# ---------------------------------------------------------------------------
# Schemas - Compatibles con frontend ProjectFileActivityRead
# ---------------------------------------------------------------------------


class FileActivityResponse(BaseModel):
    """Response estándar para eventos de actividad."""
    activity_id: str = Field(..., description="UUID del evento registrado")


class ProjectFileActivityRead(BaseModel):
    """
    Schema compatible con frontend src/api/projectFileActivityApi.ts
    """
    project_file_activity_id: str
    project_id: str
    input_file_id: Optional[str] = None
    user_id: Optional[str] = None
    user_email: str = ""
    file_event: str
    event_details: Optional[str] = None
    input_file_name: str = ""
    input_file_path: str = ""
    input_file_size_mb: Optional[float] = None
    input_file_checksum: Optional[str] = None
    file_event_created_at: str


class FileActivityListResponse(BaseModel):
    """Response paginada de actividad."""
    items: list[ProjectFileActivityRead]
    page: int = 1
    page_size: int = 50
    total_items: int = 0
    total_pages: int = 0


class InputFileEventPayload(BaseModel):
    """Payload para eventos de archivos input."""
    input_file_id: Optional[str] = None
    input_file_name: str = ""
    input_file_path: str = ""
    input_file_size_kb: Optional[float] = None
    input_file_checksum: Optional[str] = None
    event_details: Optional[dict[str, Any]] = None


class OutputFileEventPayload(BaseModel):
    """Payload para eventos de archivos output."""
    input_file_name: str = ""
    input_file_path: str = ""
    input_file_size_kb: Optional[float] = None
    input_file_checksum: Optional[str] = None
    event_details: Optional[dict[str, Any]] = None


class ProcessingEventPayload(BaseModel):
    """Payload para eventos de procesamiento."""
    processing_details: Optional[dict[str, Any]] = None
    event_details: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _validate_project_ownership(
    db: AsyncSession,
    project_id: UUID,
    auth_user_id: UUID,
) -> Project:
    """
    Valida que el usuario sea dueño del proyecto.
    
    Raises:
        HTTPException 404: Proyecto no existe
        HTTPException 403: Usuario no es dueño
    """
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    
    if project.auth_user_id != auth_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return project


def _bytes_to_mb(size_bytes: Optional[int]) -> Optional[float]:
    """Convierte bytes a MB (redondeado a 4 decimales)."""
    if size_bytes is None:
        return None
    return round(size_bytes / (1024 * 1024), 4)


def _resolve_file_event(activity) -> str:
    """
    Resuelve el file_event string para el frontend.
    Prioriza details.file_event, fallback a mapeo por event_type.
    """
    # 1. Preferir file_event guardado en details
    if activity.details and isinstance(activity.details, dict):
        file_event = activity.details.get("file_event")
        if file_event and isinstance(file_event, str):
            return file_event
    
    # 2. Fallback: mapear desde event_type
    event_type_value = (
        activity.event_type.value 
        if hasattr(activity.event_type, 'value') 
        else str(activity.event_type)
    )
    return EVENT_TYPE_TO_FILE_EVENT.get(event_type_value, f"unknown_{event_type_value}")


def _map_activity_to_frontend(activity) -> ProjectFileActivityRead:
    """
    Mapea modelo ProductFileActivity al schema del frontend.
    """
    details = activity.details or {}
    
    return ProjectFileActivityRead(
        project_file_activity_id=str(activity.product_file_activity_id),
        project_id=str(activity.project_id),
        input_file_id=details.get("input_file_id") if isinstance(details, dict) else None,
        user_id=str(activity.event_by) if activity.event_by else None,
        user_email="",  # No hay email en SSOT
        file_event=_resolve_file_event(activity),
        event_details=json.dumps(details) if details else None,
        input_file_name=activity.snapshot_name or "",
        input_file_path=activity.snapshot_path or "",
        input_file_size_mb=_bytes_to_mb(activity.snapshot_size_bytes),
        input_file_checksum=details.get("checksum") if isinstance(details, dict) else None,
        file_event_created_at=activity.event_at.isoformat() if activity.event_at else "",
    )


def _kb_to_bytes(kb: Optional[float]) -> Optional[int]:
    """Convierte KB a bytes."""
    if kb is None:
        return None
    return int(kb * 1024)


async def _log_activity(
    db: AsyncSession,
    *,
    project_id: UUID,
    auth_user_id: UUID,
    event_type: ProductFileEvent,
    file_event: str,
    snapshot_name: Optional[str] = None,
    snapshot_path: Optional[str] = None,
    snapshot_size_bytes: Optional[int] = None,
    details: Optional[dict] = None,
) -> str:
    """
    Persiste evento en product_file_activity y retorna activity_id.
    
    Args:
        auth_user_id: SSOT - dueño del evento (JWT.sub)
        file_event: String del frontend (ej. 'input_file_uploaded') guardado en details.
    """
    # Guardar file_event en details para recuperarlo en GET
    merged_details = {**(details or {}), "file_event": file_event}
    
    entry = await activity_repo.log_activity(
        db,
        auth_user_id=auth_user_id,
        project_id=project_id,
        product_file_id=None,
        event_type=event_type,
        event_by=auth_user_id,
        snapshot_name=snapshot_name,
        snapshot_path=snapshot_path,
        snapshot_size_bytes=snapshot_size_bytes,
        details=merged_details,
    )
    await db.commit()
    
    # DEBUG level para evitar rate limit en uploads masivos
    logger.debug("Activity logged: %s for project %s", file_event, project_id)
    
    return str(entry.product_file_activity_id)


# ---------------------------------------------------------------------------
# GET - Listar actividad
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=FileActivityListResponse,
    summary="Listar actividad de archivos del proyecto",
)
async def list_file_activity(
    project_id: UUID,
    order_by: str = Query("event_at", description="Campo para ordenar"),
    order_dir: str = Query("desc", description="Dirección: asc o desc"),
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(50, ge=1, le=100, description="Tamaño de página"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """
    Lista la actividad de archivos de un proyecto.
    
    Valida ownership del proyecto antes de listar.
    """
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    # Calcular offset para paginación
    offset = (page - 1) * page_size
    limit = page_size
    
    # Obtener registros del repositorio
    all_activities = await activity_repo.list_by_project(
        db,
        project_id,
        limit=limit + offset + 1,  # +1 para saber si hay más
    )
    
    # Aplicar paginación manual (el repo ya ordena por event_at desc)
    paged_activities = list(all_activities)[offset:offset + page_size]
    total_items = len(all_activities)
    total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0
    
    items = [_map_activity_to_frontend(a) for a in paged_activities]
    
    logger.info(
        "list_file_activity project_id=%s user=%s page=%d items=%d",
        str(project_id)[:8] + "...",
        str(ctx.auth_user_id)[:8] + "...",
        page,
        len(items),
    )
    
    return FileActivityListResponse(
        items=items,
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# INPUT FILE EVENTS (10 rutas)
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log file upload event",
)
async def log_upload(
    project_id: UUID,
    payload: InputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de upload de archivo."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.uploaded,
        file_event="input_file_uploaded",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        snapshot_size_bytes=_kb_to_bytes(payload.input_file_size_kb),
        details=payload.event_details,
    )
    
    logger.info(
        "file_activity_upload project=%s file=%s activity=%s",
        str(project_id)[:8] + "...",
        payload.input_file_name,
        activity_id[:8] + "...",
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/download",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log file download event",
)
async def log_download(
    project_id: UUID,
    payload: InputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de download de archivo."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.downloaded,
        file_event="input_file_downloaded",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        snapshot_size_bytes=_kb_to_bytes(payload.input_file_size_kb),
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/delete",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log file delete event",
)
async def log_delete(
    project_id: UUID,
    payload: InputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de delete de archivo."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.deleted,
        file_event="input_file_deleted",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        snapshot_size_bytes=_kb_to_bytes(payload.input_file_size_kb),
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/restore",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log file restore event",
)
async def log_restore(
    project_id: UUID,
    payload: InputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de restore de archivo."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    # Use 'updated' as closest semantic match for restore
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.updated,
        file_event="input_file_restored",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        snapshot_size_bytes=_kb_to_bytes(payload.input_file_size_kb),
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/rename",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log file rename event",
)
async def log_rename(
    project_id: UUID,
    old_name: str = Query(..., description="Nombre anterior"),
    new_name: str = Query(..., description="Nombre nuevo"),
    input_file_id: str = Query(..., description="ID del archivo"),
    input_file_path: str = Query(..., description="Ruta del archivo"),
    payload: Optional[InputFileEventPayload] = None,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de rename de archivo."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.updated,
        file_event="input_file_renamed",
        snapshot_name=new_name,
        snapshot_path=input_file_path,
        details={
            "old_name": old_name,
            "new_name": new_name,
            "input_file_id": input_file_id,
        },
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/replace",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log file replace event",
)
async def log_replace(
    project_id: UUID,
    payload: InputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de replace de archivo."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.updated,
        file_event="input_file_replaced",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        snapshot_size_bytes=_kb_to_bytes(payload.input_file_size_kb),
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/bulk/upload",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log bulk upload event",
)
async def log_bulk_upload(
    project_id: UUID,
    payload: InputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de bulk upload."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.uploaded,
        file_event="input_files_bulk_uploaded",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        snapshot_size_bytes=_kb_to_bytes(payload.input_file_size_kb),
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/bulk/delete",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log bulk delete event",
)
async def log_bulk_delete(
    project_id: UUID,
    payload: InputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de bulk delete."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.deleted,
        file_event="input_files_bulk_deleted",
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/bulk/download",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log bulk download event",
)
async def log_bulk_download(
    project_id: UUID,
    zip_name: str = Query(..., description="Nombre del ZIP"),
    zip_path: str = Query(..., description="Ruta del ZIP"),
    payload: Optional[InputFileEventPayload] = None,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de bulk download."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.downloaded,
        file_event="input_files_bulk_downloaded",
        snapshot_name=zip_name,
        snapshot_path=zip_path,
    )
    
    return FileActivityResponse(activity_id=activity_id)


# ---------------------------------------------------------------------------
# OUTPUT FILE EVENTS (4 rutas)
# ---------------------------------------------------------------------------


@router.post(
    "/output/generated",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log output file generated event",
)
async def log_output_generated(
    project_id: UUID,
    payload: OutputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de generación de archivo output."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.generated,
        file_event="output_file_generated",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        snapshot_size_bytes=_kb_to_bytes(payload.input_file_size_kb),
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/output/downloaded",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log output file downloaded event",
)
async def log_output_downloaded(
    project_id: UUID,
    payload: OutputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de descarga de archivo output."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.downloaded,
        file_event="output_file_downloaded",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        snapshot_size_bytes=_kb_to_bytes(payload.input_file_size_kb),
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/output/bulk/generated",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log bulk output generated event",
)
async def log_output_bulk_generated(
    project_id: UUID,
    payload: OutputFileEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de generación bulk de archivos output."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.generated,
        file_event="output_files_bulk_generated",
        snapshot_name=payload.input_file_name,
        snapshot_path=payload.input_file_path,
        details=payload.event_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/output/bulk/downloaded",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log bulk output downloaded event",
)
async def log_output_bulk_downloaded(
    project_id: UUID,
    zip_name: str = Query(..., description="Nombre del ZIP"),
    zip_path: str = Query(..., description="Ruta del ZIP"),
    payload: Optional[OutputFileEventPayload] = None,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de descarga bulk de archivos output."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.downloaded,
        file_event="output_files_bulk_downloaded",
        snapshot_name=zip_name,
        snapshot_path=zip_path,
    )
    
    return FileActivityResponse(activity_id=activity_id)


# ---------------------------------------------------------------------------
# PROCESSING EVENTS (3 rutas)
# ---------------------------------------------------------------------------


@router.post(
    "/processing/started",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log processing started event",
)
async def log_processing_started(
    project_id: UUID,
    payload: ProcessingEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de inicio de procesamiento."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.processing,
        file_event="project_processing_started",
        details={**(payload.processing_details or {}), **(payload.event_details or {})},
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/processing/completed",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log processing completed event",
)
async def log_processing_completed(
    project_id: UUID,
    payload: ProcessingEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de procesamiento completado."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.completed,
        file_event="project_processing_completed",
        details={**(payload.processing_details or {}), **(payload.event_details or {})},
    )
    
    return FileActivityResponse(activity_id=activity_id)


@router.post(
    "/processing/failed",
    response_model=FileActivityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log processing failed event",
)
async def log_processing_failed(
    project_id: UUID,
    payload: ProcessingEventPayload,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
):
    """Registra evento de procesamiento fallido."""
    await _validate_project_ownership(db, project_id, ctx.auth_user_id)
    
    activity_id = await _log_activity(
        db,
        project_id=project_id,
        auth_user_id=ctx.auth_user_id,
        event_type=ProductFileEvent.failed,
        file_event="project_processing_failed",
        details={**(payload.processing_details or {}), **(payload.event_details or {})},
    )
    
    logger.warning(
        "file_activity_processing_failed project=%s activity=%s details=%s",
        str(project_id)[:8] + "...",
        activity_id[:8] + "...",
        payload.processing_details,
    )
    
    return FileActivityResponse(activity_id=activity_id)


# Fin del archivo backend/app/modules/files/routes/project_file_activity_routes.py
