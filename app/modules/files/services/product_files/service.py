
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/product_files/service.py

Servicios de alto nivel para gestionar archivos PRODUCTO.

Responsabilidades:
- Crear/actualizar ProductFile (upsert por project_id + storage_path).
- Crear el registro asociado en `files_base`.
- Registrar/actualizar metadatos enriquecidos.
- Exponer operaciones de lectura, listado y archivado.

Decisiones Files v2:
- Async only.
- Acceso a datos vía repositorios:
    - product_file_repository
    - product_file_metadata_repository
    - files_base_repository

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import (
    ProductFileType,
)
from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.models.product_file_metadata_models import ProductFileMetadata
from app.modules.files.models.files_base_models import FilesBase
from app.modules.files.repositories import (
    product_file_repository,
    product_file_metadata_repository,
    files_base_repository,
)
from app.modules.files.schemas.product_file_schemas import ProductFileCreate


async def create_or_update_product_file(
    session: AsyncSession,
    *,
    auth_user_id: UUID,
    data: ProductFileCreate,
    file_type: ProductFileType,
    mime_type: str,
    file_size_bytes: int,
) -> tuple[ProductFile, FilesBase]:
    """
    Crea o actualiza un ProductFile para un proyecto y una ruta de storage.

    - Usa `upsert_by_project_and_path` en el repositorio de ProductFile.
    - Si el ProductFile no tiene `file_id`, crea el registro correspondiente
      en `files_base` y vincula ambas entidades.

    NOTA:
    - No hace commit; sólo flush.
    """
    product_file = await product_file_repository.upsert_by_project_and_path(
        session=session,
        data=data,
        file_type=file_type,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
    )

    if product_file.file_id is not None:
        # Ya está vinculado a files_base
        files_base = await files_base_repository.get_by_file_id(
            session=session,
            file_id=product_file.file_id,
        )
        if files_base is None:
            # Caso raro: hay file_id pero no existe en files_base (inconsistencia)
            files_base = await files_base_repository.create_for_product_file(
                session=session,
                auth_user_id=auth_user_id,
                project_id=product_file.project_id,
                product_file_id=product_file.product_file_id,
            )
            product_file.file_id = files_base.file_id
    else:
        # Crear files_base y vincular
        files_base = await files_base_repository.create_for_product_file(
            session=session,
            auth_user_id=auth_user_id,
            project_id=product_file.project_id,
            product_file_id=product_file.product_file_id,
        )
        product_file.file_id = files_base.file_id

    await session.flush()
    return product_file, files_base


async def register_product_file_metadata(
    session: AsyncSession,
    *,
    product_file_id: UUID,
    metadata_kwargs: dict,
) -> ProductFileMetadata:
    """
    Registra o actualiza metadatos de un ProductFile.

    `metadata_kwargs` permite pasar los parámetros esperados por
    `product_file_metadata_repository.upsert_metadata`.

    Ejemplo de uso:
        await register_product_file_metadata(
            session=session,
            product_file_id=pf.product_file_id,
            metadata_kwargs={
                "generation_method": GenerationMethod.rag_pipeline,
                "generation_params": {...},
                "page_count": 12,
                ...
            },
        )
    """
    return await product_file_metadata_repository.upsert_metadata(
        session=session,
        product_file_id=product_file_id,
        **metadata_kwargs,
    )


async def get_product_file(
    session: AsyncSession,
    product_file_id: UUID,
) -> Optional[ProductFile]:
    """
    Obtiene un ProductFile por su ID.
    """
    return await product_file_repository.get_by_id(
        session=session,
        file_id=product_file_id,
    )


async def list_active_product_files(
    session: AsyncSession,
    project_id: UUID,
    *,
    file_type: Optional[ProductFileType] = None,
    sort_by: str = "display_name",
    sort_order: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> Sequence[ProductFile]:
    """
    Lista archivos producto activos para un proyecto, con filtros básicos.
    """
    return await product_file_repository.list_active(
        session=session,
        project_id=project_id,
        file_type=file_type,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


async def archive_product_file(
    session: AsyncSession,
    product_file_id: UUID,
) -> Optional[ProductFile]:
    """
    Marca un ProductFile como archivado (y lo desactiva).
    """
    return await product_file_repository.archive(
        session=session,
        file_id=product_file_id,
    )


__all__ = [
    "create_or_update_product_file",
    "register_product_file_metadata",
    "get_product_file",
    "list_active_product_files",
    "archive_product_file",
]

# Fin del archivo backend/app/modules/files/services/product_files/service.py