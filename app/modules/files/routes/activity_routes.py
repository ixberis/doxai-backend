
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/routes/activity_routes.py

Rutas v2 de actividad de archivos PRODUCTO en el módulo Files.

Incluye:
- Registro de eventos de actividad para archivos producto.
- Consulta de historial de actividad por archivo.
- Consulta de actividad reciente por proyecto.
- Consulta de estadísticas simples de actividad por proyecto.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db  # Asumimos AsyncSession
from app.modules.files.enums import ProductFileEvent
from app.modules.files.services.product_file_activity import (
    log_product_file_event,
    list_activity_for_product_file,
    list_activity_for_project,
)
from app.modules.files.services import activity_stats_service

router = APIRouter(tags=["files:activity"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ActivityLogRequest(BaseModel):
    project_id: UUID = Field(..., description="Proyecto al que pertenece el archivo")
    event_type: ProductFileEvent = Field(
        ..., description="Tipo de evento (downloaded, generated, etc.)"
    )
    performed_by: Optional[UUID] = Field(
        default=None, description="Usuario que realiza la acción"
    )
    details: Optional[dict] = Field(
        default=None, description="Información adicional del evento"
    )


class ActivityEntry(BaseModel):
    activity_id: Optional[int] = None
    project_id: Optional[UUID] = None
    product_file_id: Optional[UUID] = None
    event_type: ProductFileEvent
    event_at: str
    event_by: Optional[UUID] = None
    snapshot_name: Optional[str] = None
    snapshot_path: Optional[str] = None
    snapshot_mime_type: Optional[str] = None
    snapshot_size_bytes: Optional[int] = None
    details: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_event_type(event_value) -> str:
    """
    Normaliza event_type a su forma canónica lowercase.
    
    Acepta:
    - ProductFileEvent enum instance → .value
    - String con alias (ej. "PRODUCT_FILE_GENERATED") → busca y devuelve valor lowercase
    - String lowercase directo → passthrough
    """
    # Si ya es un enum, devolver su valor
    if isinstance(event_value, ProductFileEvent):
        return event_value.value
    
    # Si es string, intentar convertir vía el enum (maneja aliases)
    if isinstance(event_value, str):
        try:
            # Esto maneja tanto valores directos como aliases
            enum_member = ProductFileEvent(event_value)
            return enum_member.value
        except ValueError:
            # Si no es un valor válido del enum, intentar por nombre/alias
            try:
                enum_member = ProductFileEvent[event_value]
                return enum_member.value
            except KeyError:
                # Fallback: devolver tal cual
                return event_value
    
    return str(event_value)


# ---------------------------------------------------------------------------
# Helpers DI
# ---------------------------------------------------------------------------


# Usar get_db directamente como dependencia, sin wrapper que intente awaitar un generator


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/product/{product_file_id}/log",
    summary="Registrar evento de actividad para un archivo producto",
    status_code=status.HTTP_201_CREATED,
)
async def log_activity(
    product_file_id: UUID,
    payload: ActivityLogRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Registra un evento de actividad para un archivo producto.

    Este endpoint es genérico y se puede usar para:
    - download
    - preview
    - regenerate
    - etc.
    """
    entry = await log_product_file_event(
        session=db,
        project_id=payload.project_id,
        product_file_id=product_file_id,
        event_type=payload.event_type,
        event_by=payload.performed_by,
        details=payload.details,
    )
    return {"activity_id": entry.product_file_activity_id}


@router.get(
    "/product/{product_file_id}/history",
    summary="Historial de actividad para un archivo producto",
    response_model=List[ActivityEntry],
)
async def product_history(
    product_file_id: UUID,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve los eventos recientes para un archivo producto.
    """
    rows = await list_activity_for_product_file(
        session=db,
        product_file_id=product_file_id,
        limit=limit,
    )
    result = []
    for row in rows:
        # Soportar tanto objetos ORM como dicts (para tests)
        if isinstance(row, dict):
            normalized_row = {
                **row,
                "event_type": _normalize_event_type(row.get("event_type")),
                # Proporcionar defaults para campos requeridos si faltan (para mocks de tests)
                "event_at": row.get("event_at", datetime.now(timezone.utc).isoformat()),
            }
            result.append(ActivityEntry(**normalized_row))
        else:
            result.append(
                ActivityEntry(
                    activity_id=row.product_file_activity_id,
                    project_id=row.project_id,
                    product_file_id=row.product_file_id,
                    event_type=_normalize_event_type(row.event_type),
                    event_at=row.event_at.isoformat() if hasattr(row.event_at, "isoformat") else row.event_at,
                    event_by=row.event_by,
                    snapshot_name=row.snapshot_name,
                    snapshot_path=row.snapshot_path,
                    snapshot_mime_type=row.snapshot_mime_type,
                    snapshot_size_bytes=row.snapshot_size_bytes,
                    details=row.details,
                )
            )
    return result


@router.get(
    "/project/{project_id}/recent",
    summary="Actividad reciente de archivos producto en un proyecto",
    response_model=List[ActivityEntry],
)
async def project_recent_activity(
    project_id: UUID,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve actividad reciente de archivos producto en un proyecto.
    """
    rows = await list_activity_for_project(
        session=db,
        project_id=project_id,
        limit=limit,
    )
    result = []
    for row in rows:
        # Soportar tanto objetos ORM como dicts (para tests)
        if isinstance(row, dict):
            normalized_row = {
                **row,
                "event_type": _normalize_event_type(row.get("event_type")),
                # Proporcionar defaults para campos requeridos si faltan (para mocks de tests)
                "event_at": row.get("event_at", datetime.now(timezone.utc).isoformat()),
            }
            result.append(ActivityEntry(**normalized_row))
        else:
            result.append(
                ActivityEntry(
                    activity_id=row.product_file_activity_id,
                    project_id=row.project_id,
                    product_file_id=row.product_file_id,
                    event_type=_normalize_event_type(row.event_type),
                    event_at=row.event_at.isoformat() if hasattr(row.event_at, "isoformat") else row.event_at,
                    event_by=row.event_by,
                    snapshot_name=row.snapshot_name,
                    snapshot_path=row.snapshot_path,
                    snapshot_mime_type=row.snapshot_mime_type,
                    snapshot_size_bytes=row.snapshot_size_bytes,
                    details=row.details,
                )
            )
    return result


@router.get(
    "/project/{project_id}/stats",
    summary="Estadísticas simples de actividad por proyecto",
)
async def project_activity_stats(
    project_id: UUID,
    days_back: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve un resumen simple de actividad para un proyecto en los últimos `days_back` días.
    """
    try:
        stats = await activity_stats_service.get_project_activity_stats(
            session=db,
            project_id=project_id,
            days_back=days_back,
        )
        return stats
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


# Fin del archivo backend/app/modules/files/routes/activity_routes.py
