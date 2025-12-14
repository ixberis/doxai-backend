
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/repositories/input_file_metadata_repository.py

Repositorio async para la tabla `input_file_metadata`.

Responsabilidades:
- Crear/actualizar metadatos de archivos insumo.
- Recuperar metadatos por input_file_id.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import ChecksumAlgo, InputProcessingStatus
from app.modules.files.models.input_file_metadata_models import InputFileMetadata


async def get_by_input_file_id(
    session: AsyncSession,
    input_file_id: UUID,
) -> Optional[InputFileMetadata]:
    """
    Obtiene metadatos de un archivo insumo por su ID.
    """
    stmt = select(InputFileMetadata).where(
        InputFileMetadata.input_file_id == input_file_id
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_metadata(
    session: AsyncSession,
    *,
    input_file_id: UUID,
    parser_version: str | None = None,
    checksum_algo: ChecksumAlgo | None = None,
    checksum: str | None = None,
    extracted_at=None,
    processed_at=None,
    error_message: str | None = None,
    validation_status: InputProcessingStatus | None = None,
) -> InputFileMetadata:
    """
    Crea o actualiza metadatos de un InputFile.

    NOTA:
    - No hace commit, sólo flush.
    """
    obj = await get_by_input_file_id(session, input_file_id)

    if obj is None:
        obj = InputFileMetadata(
            input_file_id=input_file_id,
            parser_version=parser_version,
            checksum_algo=checksum_algo,
            checksum=checksum,
            extracted_at=extracted_at,
            processed_at=processed_at,
            error_message=error_message,
        )
        session.add(obj)
    else:
        if parser_version is not None:
            obj.parser_version = parser_version
        if checksum_algo is not None:
            obj.checksum_algo = checksum_algo
        if checksum is not None:
            obj.checksum = checksum
        if extracted_at is not None:
            obj.extracted_at = extracted_at
        if processed_at is not None:
            obj.processed_at = processed_at
        if error_message is not None:
            obj.error_message = error_message

    if validation_status is not None:
        # si en el futuro se añade columna en metadata, aquí se ajusta;
        # por ahora, se asume que el estado vive en InputFile.
        pass

    await session.flush()
    return obj


__all__ = [
    "get_by_input_file_id",
    "upsert_metadata",
]

# Fin del archivo backend/app/modules/files/repositories/input_file_metadata_repository.py