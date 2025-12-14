
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/repositories/product_file_metadata_repository.py

Repositorio async para la tabla `product_file_metadata`.

Responsabilidades:
- CRUD básico de metadatos de archivos producto.
- Soporte para actualización durante pipeline RAG y revisión.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import (
    GenerationMethod,
    ChecksumAlgo,
)
from app.modules.files.models.product_file_metadata_models import ProductFileMetadata


async def get_by_product_file_id(
    session: AsyncSession,
    product_file_id: UUID,
) -> Optional[ProductFileMetadata]:
    """
    Obtiene metadatos de un ProductFile por su ID.
    """
    stmt = select(ProductFileMetadata).where(
        ProductFileMetadata.product_file_id == product_file_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_metadata(
    session: AsyncSession,
    *,
    product_file_id: UUID,
    generation_method: GenerationMethod | None = None,
    generation_params: Dict[str, Any] | None = None,
    ragmodel_version_used: str | None = None,
    page_count: int | None = None,
    word_count: int | None = None,
    keywords: Dict[str, Any] | None = None,
    entities: Dict[str, Any] | None = None,
    sections: Dict[str, Any] | None = None,
    summary: str | None = None,
    checksum_algo: ChecksumAlgo | None = None,
    checksum: str | None = None,
) -> ProductFileMetadata:
    """
    Crea o actualiza metadatos para un ProductFile.

    NOTA:
    - No hace commit; sólo flush.
    """
    obj = await get_by_product_file_id(session, product_file_id)

    if obj is None:
        obj = ProductFileMetadata(
            product_file_id=product_file_id,
            generation_method=generation_method or GenerationMethod.manual,  # type: ignore[arg-type]
            generation_params=generation_params,
            ragmodel_version_used=ragmodel_version_used,
            page_count=page_count,
            word_count=word_count,
            keywords=keywords,
            entities=entities,
            sections=sections,
            summary=summary,
            checksum_algo=checksum_algo,
            checksum=checksum,
        )
        session.add(obj)
    else:
        if generation_method is not None:
            obj.generation_method = generation_method
        if generation_params is not None:
            obj.generation_params = generation_params
        if ragmodel_version_used is not None:
            obj.ragmodel_version_used = ragmodel_version_used
        if page_count is not None:
            obj.page_count = page_count
        if word_count is not None:
            obj.word_count = word_count
        if keywords is not None:
            obj.keywords = keywords
        if entities is not None:
            obj.entities = entities
        if sections is not None:
            obj.sections = sections
        if summary is not None:
            obj.summary = summary
        if checksum_algo is not None:
            obj.checksum_algo = checksum_algo
        if checksum is not None:
            obj.checksum = checksum

    await session.flush()
    return obj


__all__ = [
    "get_by_product_file_id",
    "upsert_metadata",
]

# Fin del archivo backend/app/modules/files/repositories/product_file_metadata_repository.py