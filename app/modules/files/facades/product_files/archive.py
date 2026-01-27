
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
from app.modules.files.repositories import product_file_repository


async def archive_product_file(
    db: AsyncSession,
    storage_client: AsyncStorageClient,
    bucket_name: str,
    *,
    product_file_id: UUID,
    hard_delete: bool = True,
) -> None:
    """
    Elimina un archivo producto (idempotente).

    Si `hard_delete` es True (por defecto):
        - Elimina el archivo del storage (Supabase).
        - Invalida lógicamente el registro en BD (preserva histórico).

    Si `hard_delete` es False (modo legacy/compat):
        - Marca el archivo como archivado y no activo en BD.
        - El archivo se conserva en el storage.

    IDEMPOTENCIA:
    - Si el archivo ya está invalidado (storage_state != 'present' o is_active=false),
      retorna sin error (204 implícito).
    - Si el archivo no existe en storage, se trata como éxito.
    - Cualquier otro error de storage lanza FileStorageError.
    
    Lanza FileNotFoundError si el archivo no existe en BD.
    """
    import logging
    from app.modules.files.enums import FileStorageState
    
    _logger = logging.getLogger("files.delete")
    
    # Lookup sin filtros de estado (incluye inactivos/missing)
    obj = await get_product_file(
        session=db,
        product_file_id=product_file_id,
    )
    if obj is None:
        raise FileNotFoundError("No se encontró el archivo producto solicitado")

    # --- IDEMPOTENCIA: si ya está invalidado, retornar early ---
    already_invalidated = (
        obj.storage_state != FileStorageState.present
        or not obj.product_file_is_active
    )
    if already_invalidated:
        _logger.info(
            "delete_idempotent_already_missing: product_file_id=%s storage_state=%s is_active=%s",
            str(product_file_id)[:8],
            obj.storage_state.value if obj.storage_state else "null",
            obj.product_file_is_active,
        )
        return  # Éxito idempotente, nada que hacer

    if hard_delete:
        # 1) Eliminar del storage (idempotente si no existe)
        storage_path = obj.product_file_storage_path
        try:
            await delete_file_from_storage(
                storage_client,
                bucket=bucket_name,
                key=storage_path,
            )
            _logger.info(
                "storage_delete_ok: bucket=%s path=%s",
                bucket_name,
                storage_path[:60] if storage_path else "<none>",
            )
        except Exception as exc:
            error_str = str(exc).lower()
            # Tratar "not found" como idempotente
            if "not found" in error_str or "404" in error_str or "does not exist" in error_str:
                _logger.info(
                    "storage_delete_idempotent: bucket=%s path=%s (already deleted or never existed)",
                    bucket_name,
                    storage_path[:60] if storage_path else "<none>",
                )
            else:
                raise FileStorageError(
                    f"No se pudo eliminar el archivo producto del storage: {exc}"
                ) from exc
        
        # 2) Invalidación lógica en BD (NO hard-delete para preservar histórico)
        invalidated = await product_file_repository.invalidate_for_deletion(
            session=db,
            product_file_id=product_file_id,
            reason="user_deleted",
        )
        if invalidated:
            _logger.info(
                "db_logical_invalidation_ok: product_file_id=%s storage_state=missing",
                str(product_file_id)[:8],
            )
    else:
        # Modo legacy: solo archivado lógico
        await archive_product_file_service(
            session=db,
            product_file_id=product_file_id,
        )


__all__ = ["archive_product_file"]

# Fin del archivo backend/app/modules/files/facades/product_files/archive.py