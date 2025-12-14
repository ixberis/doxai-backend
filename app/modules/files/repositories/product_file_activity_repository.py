
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/repositories/product_file_activity_repository.py

Repositorio async para la tabla `product_file_activity`.

Responsabilidades:
- Registrar eventos de actividad sobre archivos producto.
- Consultar historial de actividad por archivo o por proyecto.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import ProductFileEvent
from app.modules.files.models.product_file_activity_models import ProductFileActivity


async def log_activity(
    session: AsyncSession,
    *,
    project_id: UUID,
    product_file_id: UUID | None,
    event_type: ProductFileEvent,
    event_by: UUID | None,
    snapshot_name: str | None = None,
    snapshot_path: str | None = None,
    snapshot_mime_type: str | None = None,
    snapshot_size_bytes: int | None = None,
    details: dict | None = None,
    event_at: datetime | None = None,
) -> ProductFileActivity:
    """
    Registra un evento de actividad para un ProductFile.
    """
    obj = ProductFileActivity(
        project_id=project_id,
        product_file_id=product_file_id,
        event_type=event_type,
        event_at=event_at,
        event_by=event_by,
        snapshot_name=snapshot_name,
        snapshot_path=snapshot_path,
        snapshot_mime_type=snapshot_mime_type,
        snapshot_size_bytes=snapshot_size_bytes,
        details=details,
    )
    session.add(obj)
    await session.flush()
    return obj


async def list_by_product_file(
    session: AsyncSession,
    product_file_id: UUID,
    *,
    limit: int = 100,
) -> Sequence[ProductFileActivity]:
    """
    Lista actividad reciente para un archivo producto.
    """
    safe_limit = max(1, min(1000, int(limit)))
    stmt = (
        select(ProductFileActivity)
        .where(ProductFileActivity.product_file_id == product_file_id)
        .order_by(ProductFileActivity.event_at.desc())
        .limit(safe_limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def list_by_project(
    session: AsyncSession,
    project_id: UUID,
    *,
    limit: int = 500,
) -> Sequence[ProductFileActivity]:
    """
    Lista actividad reciente en todo un proyecto.
    """
    safe_limit = max(1, min(5000, int(limit)))
    stmt = (
        select(ProductFileActivity)
        .where(ProductFileActivity.project_id == project_id)
        .order_by(ProductFileActivity.event_at.desc())
        .limit(safe_limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


__all__ = [
    "log_activity",
    "list_by_product_file",
    "list_by_project",
]

# Fin del archivo backend/app/modules/files/repositories/product_file_activity_repository.py