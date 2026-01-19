
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/product_files/create.py

Fachada funcional para crear o actualizar archivos PRODUCTO.

Responsabilidades:
- Subir bytes al storage.
- Inferir ProductFileType a partir de MIME/filename cuando no se especifica.
- Llamar al servicio de dominio `create_or_update_product_file`.
- Registrar metadatos enriquecidos (generation_method, params, etc.) cuando aplique.
- Devolver un ProductFileResponse listo para exponer vía API.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import (
    FileLanguage,
    ProductFileType,
    ProductVersion,
    StorageBackend,
    GenerationMethod,
)
from app.modules.files.facades.errors import FileStorageError
from app.modules.files.schemas import ProductFileCreate, ProductFileResponse
from app.modules.files.services import (
    create_or_update_product_file,
    register_product_file_metadata,
)
from app.modules.files.services.product_file_type_mapper import guess_product_type
from app.modules.files.services.storage_ops_service import (
    AsyncStorageClient,
    upload_file_bytes,
)


async def create_product_file(
    db: AsyncSession,
    storage_client: AsyncStorageClient,
    bucket_name: str,
    *,
    project_id: UUID,
    auth_user_id: UUID,
    generated_by: UUID,
    file_bytes: bytes,
    storage_key: str,
    original_name: str,
    mime_type: str,
    display_name: Optional[str] = None,
    language: Optional[FileLanguage] = None,
    version: ProductVersion = ProductVersion.v1,
    file_type: Optional[ProductFileType] = None,
    storage_backend: StorageBackend = StorageBackend.supabase,
    generation_method: Optional[GenerationMethod] = None,
    generation_params: Optional[Dict[str, Any]] = None,
    ragmodel_version_used: Optional[str] = None,
) -> ProductFileResponse:
    """
    Crea (o actualiza) un archivo producto a partir de bytes.

    Args:
        auth_user_id: UUID del usuario autenticado (de ctx.auth_user_id).
        generated_by: UUID del generador (metadata de negocio, puede diferir de auth).

    Flujo:
    1. Sube el archivo a storage.
    2. Determina el ProductFileType si no se proporciona.
    3. Crea/actualiza el ProductFile en BD.
    4. Opcionalmente registra metadatos enriquecidos.
    5. Devuelve un ProductFileResponse.

    NOTA:
    - No realiza commit; sólo hace flush sobre la AsyncSession.
    - Si el storage falla, lanza FileStorageError.
    """
    size_bytes = len(file_bytes or b"")

    # 1) Subir al storage
    try:
        await upload_file_bytes(
            storage_client,
            bucket=bucket_name,
            key=storage_key,
            data=file_bytes,
            mime_type=mime_type,
        )
    except Exception as exc:  # pragma: no cover - defensivo
        raise FileStorageError(
            f"No se pudo subir el archivo producto al storage: {exc}"
        ) from exc

    # 2) Determinar tipo lógico si no se pasó explícito
    effective_file_type = file_type or guess_product_type(
        mime_type=mime_type,
        filename=original_name,
    )

    # 3) Construir DTO y crear/actualizar ProductFile
    create_dto = ProductFileCreate(
        project_id=project_id,
        product_file_name=original_name,
        product_file_display_name=display_name,
        product_file_mime_type=mime_type,
        product_file_size_bytes=size_bytes,
        product_file_type=effective_file_type,
        product_file_version=version,
        product_file_language=language,
        product_file_storage_backend=storage_backend,
        product_file_storage_path=storage_key,
        generated_by=generated_by,
    )

    product_file, _ = await create_or_update_product_file(
        session=db,
        auth_user_id=auth_user_id,
        data=create_dto,
        file_type=effective_file_type,
        mime_type=mime_type,
        file_size_bytes=size_bytes,
    )

    # 4) Registrar metadatos enriquecidos, si aplica
    if generation_method or generation_params or ragmodel_version_used:
        metadata_kwargs: Dict[str, Any] = {}
        if generation_method is not None:
            metadata_kwargs["generation_method"] = generation_method
        if generation_params is not None:
            metadata_kwargs["generation_params"] = generation_params
        if ragmodel_version_used is not None:
            metadata_kwargs["ragmodel_version_used"] = ragmodel_version_used

        await register_product_file_metadata(
            session=db,
            product_file_id=product_file.product_file_id,
            metadata_kwargs=metadata_kwargs,
        )

    # 5) Respuesta Pydantic desde ORM
    return ProductFileResponse.model_validate(product_file)


__all__ = ["create_product_file"]

# Fin del archivo backend/app/modules/files/facades/product_files/create.py