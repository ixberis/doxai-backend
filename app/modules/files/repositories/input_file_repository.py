
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
    FileStorageState,
)
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.schemas.input_file_schemas import InputFileUpload


async def get_by_id(
    session: AsyncSession,
    input_file_id: UUID,
) -> Optional[InputFile]:
    """
    Obtiene un InputFile por su input_file_id (PK).
    """
    stmt = select(InputFile).where(InputFile.input_file_id == input_file_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_by_file_id(
    session: AsyncSession,
    file_id: UUID,
) -> Optional[InputFile]:
    """
    Obtiene un InputFile por su file_id (FK a files_base).
    
    Busca directamente en input_files.file_id sin requerir JOIN con files_base.
    """
    stmt = select(InputFile).where(InputFile.file_id == file_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_by_project(
    session: AsyncSession,
    project_id: UUID,
    *,
    include_archived: bool = False,
    include_inactive: bool = False,
) -> Sequence[InputFile]:
    """Lista InputFiles de un proyecto.

    Por defecto, excluye archivos:
    - Archivados (input_file_is_archived=True)
    - Inactivos (input_file_is_active=False)
    - Eliminados lógicamente (storage_state != 'present')
    
    Args:
        include_archived: Si True, incluye archivados
        include_inactive: Si True, incluye inactivos/eliminados lógicamente
    """
    stmt = (
        select(InputFile)
        .where(InputFile.project_id == project_id)
    )
    
    # Filtrar archivos activos a menos que se pida incluir inactivos
    if not include_inactive:
        stmt = stmt.where(
            InputFile.input_file_is_active == True,
            InputFile.storage_state == FileStorageState.present,
        )
    
    # Filtrar archivados a menos que se pida incluirlos
    if not include_archived:
        stmt = stmt.where(InputFile.input_file_is_archived == False)
    
    stmt = stmt.order_by(InputFile.input_file_uploaded_at.desc())
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
    input_file_id: UUID | None = None,
) -> InputFile:
    """
    Crea un InputFile a partir de los datos de carga.

    Args:
        input_file_id: UUID pre-generado para SSOT path. Si no se pasa,
                      se genera uno nuevo automáticamente.

    NOTA:
    - No hace commit, sólo flush.
    """
    obj = InputFile(
        project_id=data.project_id,
        # SSOT: auth_user_id = ownership, uploaded_by_auth_user_id = actor
        auth_user_id=uploaded_by,
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
    # Si se proporciona un ID pre-generado, usarlo
    if input_file_id is not None:
        obj.input_file_id = input_file_id
    
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


async def invalidate_for_deletion(
    session: AsyncSession,
    *,
    input_file_id: UUID,
    reason: str = "user_deleted",
) -> Optional[InputFile]:
    """
    Invalida lógicamente un InputFile (sin borrar la fila).
    
    Usado cuando el usuario elimina un archivo:
    - storage_state='missing' (ya no existe en storage)
    - invalidated_at=now()
    - invalidation_reason=reason
    - input_file_is_active=False
    
    Idempotente: si ya está invalidado, retorna el objeto sin error.
    
    Returns:
        InputFile actualizado, o None si no existe.
    
    NOTA:
    - No hace commit, sólo flush.
    """
    from datetime import datetime, timezone
    
    obj = await get_by_id(session, input_file_id)
    if obj is None:
        return None
    
    # Idempotente: si ya está invalidado, retornar sin cambios
    if obj.storage_state == FileStorageState.missing and not obj.input_file_is_active:
        return obj
    
    obj.storage_state = FileStorageState.missing
    obj.invalidated_at = datetime.now(timezone.utc)
    obj.invalidation_reason = reason
    obj.input_file_is_active = False
    obj.input_file_is_archived = True
    
    await session.flush()
    return obj


async def hard_delete(
    session: AsyncSession,
    *,
    input_file_id: UUID,
) -> bool:
    """
    Elimina físicamente un InputFile de la base de datos.
    
    DEPRECATED: Usar invalidate_for_deletion para preservar histórico.
    Este método solo debe usarse por jobs administrativos de limpieza.
    
    También elimina el registro relacionado en files_base si existe.
    
    Returns:
        True si se eliminó correctamente, False si no existía.
    
    NOTA:
    - No hace commit, sólo ejecuta DELETE y flush.
    - files_base tiene FK con ON DELETE CASCADE si está configurado,
      pero hacemos delete explícito para ser defensivos.
    """
    from sqlalchemy import delete, text
    
    obj = await get_by_id(session, input_file_id)
    if obj is None:
        return False
    
    # Guardar file_id antes de borrar para limpiar files_base
    file_id = obj.file_id
    
    # 1) Eliminar de input_files
    await session.delete(obj)
    await session.flush()
    
    # 2) Eliminar de files_base si existe (defensivo, por si no hay CASCADE)
    if file_id is not None:
        try:
            await session.execute(
                text("DELETE FROM public.files_base WHERE file_id = CAST(:file_id AS uuid)"),
                {"file_id": str(file_id)},
            )
            await session.flush()
        except Exception:
            # Si falla (ej. ya fue eliminado por CASCADE), ignorar
            pass
    
    return True


__all__ = [
    "get_by_id",
    "get_by_file_id",
    "list_by_project",
    "create_from_upload",
    "mark_archived",
    "invalidate_for_deletion",
    "hard_delete",
]

# Fin del archivo backend/app/modules/files/repositories/input_file_repository.py