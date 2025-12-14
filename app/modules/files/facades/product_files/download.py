
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/product_files/download.py

Fachada funcional para obtener URL de descarga temporal de
archivos PRODUCTO.

Responsabilidades:
- Resolver el ProductFile por ID.
- Interactuar con el storage para generar una URL temporal.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.facades.errors import FileNotFoundError, FileStorageError
from app.modules.files.services import get_product_file
from app.modules.files.services.storage_ops_service import (
    AsyncStorageClient,
    generate_download_url,
)


async def get_product_file_download_url(
    db: AsyncSession,
    storage_client: AsyncStorageClient,
    bucket_name: str,
    *,
    product_file_id: UUID,
    expires_in_seconds: int = 3600,
) -> str:
    """
    Genera una URL de descarga temporal para un ProductFile.

    Lanza:
    - FileNotFoundError si el archivo no existe.
    - FileStorageError si el storage no puede generar la URL.
    """
    obj = await get_product_file(
        session=db,
        product_file_id=product_file_id,
    )
    if obj is None:
        raise FileNotFoundError("No se encontró el archivo producto solicitado")

    try:
        return await generate_download_url(
            storage_client,
            bucket=bucket_name,
            key=obj.product_file_storage_path,
            expires_in_seconds=expires_in_seconds,
        )
    except Exception as exc:  # pragma: no cover - defensivo
        raise FileStorageError(
            f"No se pudo generar la URL de descarga del archivo producto: {exc}"
        ) from exc


__all__ = ["get_product_file_download_url"]

# Fin del archivo backend/app/modules/files/facades/product_files/download.py