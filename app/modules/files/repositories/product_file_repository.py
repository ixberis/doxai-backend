
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/repositories/product_file_repository.py

Repositorio async para acceso a datos de archivos PRODUCTO.

Decisiones Files v2:
- AsyncSession únicamente.
- Sin commits ni refresh automáticos; la capa de servicio es responsable
  de gestionar la transacción.
- Mantiene las funciones públicas históricas:
    - get_by_id
    - upsert_by_project_and_path
    - list_active
    - archive
  pero reimplementadas en modo async y sin efectos de commit.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import (
    ProductFileType,
    ProductVersion,
    StorageBackend,
)
from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.schemas.product_file_schemas import ProductFileCreate

logger = logging.getLogger(__name__)


async def get_by_id(
    session: AsyncSession,
    file_id: UUID,
) -> Optional[ProductFile]:
    """
    Obtiene un ProductFile por su ID.
    """
    stmt = select(ProductFile).where(ProductFile.product_file_id == file_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _extract_storage_path(data: ProductFileCreate) -> str:
    """
    Determina la ruta de almacenamiento a partir del DTO.

    Preferido (Files v2):
    - data.storage_path

    Fallbacks de compatibilidad:
    - data.product_file_storage_path
    - data.product_file_gcs_path
    - data.file_storage_path
    """
    for attr in (
        "storage_path",
        "product_file_storage_path",
        "product_file_gcs_path",
        "file_storage_path",
    ):
        value = getattr(data, attr, None)
        if value:
            return value
    raise ValueError("No se pudo determinar la ruta de almacenamiento para ProductFile")


async def upsert_by_project_and_path(
    session: AsyncSession,
    data: ProductFileCreate,
    file_type: ProductFileType,
    mime_type: str,
    file_size_bytes: int,
) -> ProductFile:
    """
    Inserta o actualiza un ProductFile por (project_id, storage_path).

    Comportamiento:
    - Si existe un archivo activo con mismo proyecto y storage_path, lo actualiza.
    - Si no existe, crea un registro nuevo.

    NOTA:
    - No hace commit; sólo agrega/actualiza y hace flush.
    """
    from sqlalchemy import and_

    storage_path = _extract_storage_path(data)

    stmt = select(ProductFile).where(
        and_(
            ProductFile.project_id == data.project_id,
            ProductFile.product_file_storage_path == storage_path,
        )
    )
    result = await session.execute(stmt)
    existing_file: Optional[ProductFile] = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing_file:
        # Actualizar archivo existente
        existing_file.product_file_display_name = (
            getattr(data, "product_file_display_name", None)
            or getattr(data, "display_name", None)
            or getattr(data, "file_name", None)
            or existing_file.product_file_display_name
        )
        existing_file.product_file_original_name = (
            getattr(data, "product_file_name", None)
            or getattr(data, "original_name", None)
            or getattr(data, "product_file_original_name", None)
            or existing_file.product_file_original_name
        )
        existing_file.product_file_type = file_type
        existing_file.product_file_mime_type = mime_type
        existing_file.product_file_size_bytes = int(file_size_bytes or 0)
        existing_file.product_file_is_archived = False
        existing_file.product_file_is_active = True
        existing_file.product_file_generated_at = now
        await session.flush()
        logger.info(
            "product_file_updated",
            extra={
                "product_file_id": str(existing_file.product_file_id),
                "project_id": str(existing_file.project_id),
                "storage_path": storage_path,
            },
        )
        return existing_file

    # Crear archivo nuevo
    obj = ProductFile(
        project_id=data.project_id,
        product_file_original_name=(
            getattr(data, "product_file_name", None)
            or getattr(data, "original_name", None)
            or getattr(data, "product_file_original_name", None)
            or getattr(data, "file_name", None)
            or storage_path
        ),
        product_file_display_name=(
            getattr(data, "product_file_display_name", None)
            or getattr(data, "display_name", None)
            or getattr(data, "file_name", None)
        ),
        product_file_type=file_type,
        product_file_mime_type=mime_type,
        product_file_size_bytes=int(file_size_bytes or 0),
        product_file_storage_path=storage_path,
        product_file_storage_backend=(
            getattr(data, "product_file_storage_backend", None)
            or getattr(data, "storage_backend", StorageBackend.supabase)
        ),
        product_file_language=(
            getattr(data, "product_file_language", None)
            or getattr(data, "language", None)
        ),
        product_file_version=(
            getattr(data, "product_file_version", None)
            or getattr(data, "version", ProductVersion.v1)
        ),
        product_file_generated_by=data.generated_by,
        product_file_is_active=True,
        product_file_is_archived=False,
        product_file_generated_at=now,
    )
    session.add(obj)
    await session.flush()

    logger.info(
        "product_file_created",
        extra={
            "product_file_id": str(obj.product_file_id),
            "project_id": str(obj.project_id),
            "storage_path": storage_path,
        },
    )
    return obj


async def list_active(
    session: AsyncSession,
    project_id: UUID,
    file_type: Optional[ProductFileType] = None,
    sort_by: str = "display_name",
    sort_order: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> List[ProductFile]:
    """
    Lista archivos producto activos con filtros y paginación.
    """
    from sqlalchemy import and_

    conditions = [
        ProductFile.project_id == project_id,
        ProductFile.product_file_is_active.is_(True),
        ProductFile.product_file_is_archived.is_(False),
    ]
    if file_type:
        conditions.append(ProductFile.product_file_type == file_type)

    stmt = select(ProductFile).where(and_(*conditions))

    sort_map = {
        "display_name": ProductFile.product_file_display_name,
        "file_type": ProductFile.product_file_type,
        "generated_at": ProductFile.product_file_generated_at,
    }
    sort_col = sort_map.get(sort_by, ProductFile.product_file_display_name)
    stmt = stmt.order_by(desc(sort_col) if sort_order == "desc" else asc(sort_col))

    # clamp de limit/offset
    safe_limit = max(1, min(1000, int(limit)))
    safe_offset = max(0, int(offset))
    stmt = stmt.limit(safe_limit).offset(safe_offset)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def archive(
    session: AsyncSession,
    file_id: UUID,
) -> Optional[ProductFile]:
    """
    Archiva un archivo producto (marcado lógico).

    NOTA:
    - No hace commit; sólo actualiza flags y hace flush.
    """
    file_obj = await get_by_id(session, file_id)
    if file_obj is None:
        return None

    file_obj.product_file_is_archived = True
    file_obj.product_file_is_active = False
    await session.flush()

    logger.info(
        "product_file_archived",
        extra={
            "product_file_id": str(file_id),
            "display_name": file_obj.product_file_display_name,
        },
    )
    return file_obj


__all__ = [
    "get_by_id",
    "upsert_by_project_and_path",
    "list_active",
    "archive",
]

# Fin del archivo backend/app/modules/files/repositories/product_file_repository.py

