
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/input_files/service.py

Servicios de alto nivel para gestionar archivos INSUMO en el módulo Files.

Responsabilidades:
- Orquestar la creación de InputFile a partir de un upload.
- Crear el registro asociado en `files_base`.
- Registrar metadatos iniciales (checksum, parser_version) cuando aplique.
- Exponer operaciones de lectura y archivado usadas por ruteadores/facades.

Decisiones Files v2:
- Async only (AsyncSession).
- Acceso a datos siempre vía repositorios:
    - input_file_repository
    - input_file_metadata_repository
    - files_base_repository

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import (
    StorageBackend,
)
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.input_file_metadata_models import InputFileMetadata
from app.modules.files.models.files_base_models import FilesBase
from app.modules.files.repositories import (
    input_file_repository,
    input_file_metadata_repository,
    files_base_repository,
)
from app.modules.files.schemas.input_file_schemas import InputFileUpload


async def register_uploaded_input_file(
    session: AsyncSession,
    *,
    upload: InputFileUpload,
    uploaded_by: UUID,
    storage_backend: StorageBackend,
    storage_path: str,
    file_extension: Optional[str],
    checksum: Optional[str] = None,
    parser_version: Optional[str] = None,
    input_file_id: Optional[UUID] = None,
) -> tuple[InputFile, FilesBase, Optional[InputFileMetadata]]:
    """
    Registra un archivo insumo subido por la persona usuaria.

    Esta operación:
    1. Crea el registro en `input_files`.
    2. Crea el registro canónico en `files_base` con rol = 'input'.
    3. Registra metadatos iniciales en `input_file_metadata` (opcional).

    Args:
        input_file_id: UUID pre-generado para SSOT path. Si no se pasa,
                      se genera uno nuevo en el repositorio.

    NOTA:
    - No hace commit; sólo realiza flush sobre la sesión.
    - El commit se delega a la capa de ruteador/fachada.
    """
    # 1) Crear InputFile
    input_file = await input_file_repository.create_from_upload(
        session=session,
        data=upload,
        uploaded_by=uploaded_by,
        storage_backend=storage_backend,
        storage_path=storage_path,
        file_extension=file_extension,
        input_file_id=input_file_id,
    )

    # 2) Crear FilesBase vinculado al InputFile
    files_base = await files_base_repository.create_for_input_file(
        session=session,
        auth_user_id=uploaded_by,
        project_id=upload.project_id,
        input_file_id=input_file.input_file_id,
    )

    # Vincular el file_id recién creado al InputFile
    input_file.file_id = files_base.file_id

    # 3) Metadatos iniciales (opcional)
    metadata: Optional[InputFileMetadata] = None
    if checksum or parser_version:
        metadata = await input_file_metadata_repository.upsert_metadata(
            session=session,
            input_file_id=input_file.input_file_id,
            parser_version=parser_version,
            checksum_algo=None,
            checksum=checksum,
        )

    return input_file, files_base, metadata


async def get_input_file(
    session: AsyncSession,
    input_file_id: UUID,
) -> Optional[InputFile]:
    """
    Obtiene un InputFile por su ID.
    """
    return await input_file_repository.get_by_id(session, input_file_id)


async def list_project_input_files(
    session: AsyncSession,
    project_id: UUID,
    *,
    include_archived: bool = False,
) -> Sequence[InputFile]:
    """
    Lista archivos insumo de un proyecto, con opción de incluir archivados.
    """
    return await input_file_repository.list_by_project(
        session=session,
        project_id=project_id,
        include_archived=include_archived,
    )


async def archive_input_file(
    session: AsyncSession,
    input_file_id: UUID,
) -> Optional[InputFile]:
    """
    Marca un InputFile como archivado (y lo desactiva).
    """
    return await input_file_repository.mark_archived(
        session=session,
        input_file_id=input_file_id,
        archived=True,
    )


async def unarchive_input_file(
    session: AsyncSession,
    input_file_id: UUID,
) -> Optional[InputFile]:
    """
    Revierte el archivado de un InputFile (lo vuelve activo).
    """
    return await input_file_repository.mark_archived(
        session=session,
        input_file_id=input_file_id,
        archived=False,
    )


__all__ = [
    "register_uploaded_input_file",
    "get_input_file",
    "list_project_input_files",
    "archive_input_file",
    "unarchive_input_file",
]

# Fin del archivo backend/app/modules/files/services/input_files/service.py