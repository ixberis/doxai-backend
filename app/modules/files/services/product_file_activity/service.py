
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/product_file_activity/service.py

Servicios de alto nivel para registrar y consultar actividad sobre
archivos PRODUCTO.

Responsabilidades:
- Registrar eventos en `product_file_activity`.
- Listar actividad por archivo o por proyecto.

Decisiones Files v2:
- Async only.
- Acceso a datos vía `product_file_activity_repository`.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import ProductFileEvent
from app.modules.files.models.product_file_activity_models import ProductFileActivity
from app.modules.files.repositories import product_file_activity_repository


async def log_product_file_event(
    session: AsyncSession,
    *,
    project_id: UUID,
    product_file_id: Optional[UUID],
    event_type: ProductFileEvent,
    event_by: Optional[UUID],
    snapshot_name: Optional[str] = None,
    snapshot_path: Optional[str] = None,
    snapshot_mime_type: Optional[str] = None,
    snapshot_size_bytes: Optional[int] = None,
    details: Optional[dict] = None,
    event_at: Optional[datetime] = None,
) -> ProductFileActivity:
    """
    Registra un evento de actividad para un archivo producto.
    """
    return await product_file_activity_repository.log_activity(
        session=session,
        project_id=project_id,
        product_file_id=product_file_id,
        event_type=event_type,
        event_by=event_by,
        snapshot_name=snapshot_name,
        snapshot_path=snapshot_path,
        snapshot_mime_type=snapshot_mime_type,
        snapshot_size_bytes=snapshot_size_bytes,
        details=details,
        event_at=event_at,
    )


async def list_activity_for_product_file(
    session: AsyncSession,
    product_file_id: UUID,
    *,
    limit: int = 100,
) -> Sequence[ProductFileActivity]:
    """
    Lista eventos recientes para un archivo producto.
    """
    return await product_file_activity_repository.list_by_product_file(
        session=session,
        product_file_id=product_file_id,
        limit=limit,
    )


async def list_activity_for_project(
    session: AsyncSession,
    project_id: UUID,
    *,
    limit: int = 500,
) -> Sequence[ProductFileActivity]:
    """
    Lista actividad reciente de archivos producto en un proyecto.
    """
    return await product_file_activity_repository.list_by_project(
        session=session,
        project_id=project_id,
        limit=limit,
    )


__all__ = [
    "log_product_file_event",
    "list_activity_for_product_file",
    "list_activity_for_project",
]

# Fin del archivo backend/app/modules/files/services/product_file_activity/service.py