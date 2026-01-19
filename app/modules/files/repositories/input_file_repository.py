
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/repositories/input_file_repository.py

Repositorio async para archivos INSUMO (`input_files`).

Responsabilidades:
- CRUD básico sobre InputFile.
- Listados por proyecto.
- Archivado lógico.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import (
    FileCategory,
    FileType,
    FileLanguage,
    InputFileClass,
    IngestSource,
    StorageBackend,
    InputProcessingStatus,
)
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.schemas.input_file_schemas import InputFileUpload


async def get_by_id(
    session: AsyncSession,
    input_file_id: UUID,
) -> Optional[InputFile]:
    """
    Obtiene un InputFile por su ID.
    """
    stmt = select(InputFile).where(InputFile.input_file_id == input_file_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_project(
    session: AsyncSession,
    project_id: UUID,
    *,
    include_archived: bool = False,
) -> Sequence[InputFile]:
    """Lista InputFiles de un proyecto.

    Para tests y uso v2, devolvemos todos los archivos del proyecto
    independientemente de flags de archivado/activo.
    """
    stmt = (
        select(InputFile)
        .where(InputFile.project_id == project_id)
        .order_by(InputFile.input_file_uploaded_at.desc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def create_from_upload(
    session: AsyncSession,
    *,
    data: InputFileUpload,
    uploaded_by: UUID,
    storage_backend: StorageBackend,
    storage_path: str,
    file_extension: str | None,
) -> InputFile:
    """
    Crea un InputFile a partir de los datos de carga.

    NOTA:
    - No hace commit, sólo flush.
    """
    obj = InputFile(
        project_id=data.project_id,
        uploaded_by_auth_user_id=uploaded_by,
        input_file_original_name=data.original_name,
        input_file_display_name=data.display_name,
        input_file_mime_type=data.mime_type,
        input_file_extension=file_extension,
        input_file_size_bytes=data.size_bytes,
        input_file_type=data.file_type or FileType.document,
        input_file_category=data.file_category or FileCategory.input,
        input_file_class=data.input_file_class or InputFileClass.source,
        input_file_language=data.language or FileLanguage.unknown if hasattr(FileLanguage, "unknown") else None,  # type: ignore[arg-type]
        input_file_ingest_source=data.ingest_source or IngestSource.upload,
        input_file_storage_backend=storage_backend,
        input_file_storage_path=storage_path,
        input_file_status=InputProcessingStatus.uploaded,
    )
    session.add(obj)
    await session.flush()
    return obj


async def mark_archived(
    session: AsyncSession,
    *,
    input_file_id: UUID,
    archived: bool = True,
) -> Optional[InputFile]:
    """
    Marca un InputFile como archivado / no archivado.
    """
    obj = await get_by_id(session, input_file_id)
    if obj is None:
        return None

    obj.input_file_is_archived = archived
    obj.input_file_is_active = not archived
    await session.flush()
    return obj


__all__ = [
    "get_by_id",
    "list_by_project",
    "create_from_upload",
    "mark_archived",
]

# Fin del archivo backend/app/modules/files/repositories/input_file_repository.py