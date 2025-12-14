
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/product_files/archive.py

Fachada funcional para archivar archivos PRODUCTO y, opcionalmente,
eliminar el fichero físico del storage.

Responsabilidades:
- Verificar que el ProductFile exista.
- Marcarlo como archivado (y no activo) en BD.
- Opcionalmente eliminar el archivo del storage.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.facades.errors import FileNotFoundError, FileStorageError
from app.modules.files.services import (
    get_product_file,
    archive_product_file as archive_product_file_service,
)
from app.modules.files.services.storage_ops_service import (
    AsyncStorageClient,
    delete_file_from_storage,
)


async def archive_product_file(
    db: AsyncSession,
    storage_client: AsyncStorageClient,
    bucket_name: str,
    *,
    product_file_id: UUID,
    hard_delete: bool = False,
) -> None:
    """
    Archiva un archivo producto (y opcionalmente elimina el fichero físico).

    Si `hard_delete` es False:
        - Marca el archivo como archivado y no activo en BD.

    Si `hard_delete` es True:
        - Además intenta eliminar el archivo del storage.

    Lanza FileNotFoundError si el archivo no existe.
    """
    obj = await get_product_file(
        session=db,
        product_file_id=product_file_id,
    )
    if obj is None:
        raise FileNotFoundError("No se encontró el archivo producto solicitado")

    # 1) Archivado lógico
    await archive_product_file_service(
        session=db,
        product_file_id=product_file_id,
    )

    # 2) Borrado físico opcional
    if hard_delete:
        try:
            await delete_file_from_storage(
                storage_client,
                bucket=bucket_name,
                key=obj.product_file_storage_path,
            )
        except Exception as exc:  # pragma: no cover - defensivo
            raise FileStorageError(
                f"No se pudo eliminar el archivo producto del storage: {exc}"
            ) from exc


__all__ = ["archive_product_file"]

# Fin del archivo backend/app/modules/files/facades/product_files/archive.py