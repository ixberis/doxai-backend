
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/input_files/upload.py

Fachada de alto nivel para operaciones con archivos INSUMO (Input Files).

Responsabilidades:
- Orquestar la creación de InputFile a partir de bytes subidos.
- Interactuar con el storage a través de un cliente asíncrono (AsyncStorageClient).
- Exponer operaciones de:
    - subir (upload)
    - listar por proyecto
    - obtener detalle por ID
    - generar URL de descarga
    - eliminar / archivar

Decisiones Files v2:
- Async only (AsyncSession).
- Usa servicios de dominio del módulo Files:
    - register_uploaded_input_file, list_project_input_files, archive_input_file
    - get_input_file_by_file_id
    - storage_ops_service (upload/download/delete)
- No hace commits; la transacción es responsabilidad del ruteador o
  del módulo cliente que use la fachada.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import StorageBackend
from app.modules.files.facades.errors import (
    FileNotFoundError,
    FileStorageError,
)
from app.modules.files.schemas import InputFileUpload, InputFileResponse
from app.modules.files.services import (
    register_uploaded_input_file,
    list_project_input_files,
    archive_input_file,
)
from app.modules.files.services.input_file_lookup_service import (
    get_input_file_by_file_id,
)
from app.modules.files.services.storage_ops_service import (
    AsyncStorageClient,
    upload_file_bytes,
    generate_download_url,
    delete_file_from_storage,
)


class InputFilesFacade:
    """
    Fachada de operaciones sobre archivos insumo.

    Esta clase está pensada para ser utilizada desde ruteadores HTTP
    u otros módulos (Projects, RAG, Admin) que necesiten un API estable
    de alto nivel para manipular archivos insumo.
    """

    def __init__(
        self,
        *,
        db: AsyncSession,
        storage_client: AsyncStorageClient,
        bucket_name: str,
        storage_backend: StorageBackend = StorageBackend.supabase,
    ) -> None:
        """
        Parámetros
        ----------
        db:
            AsyncSession de SQLAlchemy (inyectada por FastAPI u otra capa).
        storage_client:
            Cliente asíncrono de storage que implementa AsyncStorageClient.
        bucket_name:
            Nombre del bucket/logical container donde se guardan los
            archivos insumo.
        storage_backend:
            Enum de backend de almacenamiento. Por defecto `supabase`.
        """
        self._db = db
        self._storage = storage_client
        self._bucket = bucket_name
        self._backend = storage_backend

    # ------------------------------------------------------------------
    # Operaciones de creación / upload
    # ------------------------------------------------------------------
    async def upload_input_file(
        self,
        *,
        upload: InputFileUpload,
        uploaded_by: UUID,
        file_bytes: bytes,
        storage_key: str,
        checksum: Optional[str] = None,
        parser_version: Optional[str] = None,
    ) -> InputFileResponse:
        """
        Sube un archivo insumo al storage y registra sus metadatos en BD.

        Flujo:
        1. Sube `file_bytes` a storage usando (bucket_name, storage_key).
        2. Crea InputFile + FilesBase + (opcional) InputFileMetadata.
        3. Devuelve un InputFileResponse listo para API.

        NOTA:
        - No realiza commit; sólo hace flush en la AsyncSession.
        - Cualquier error de storage se reporta como FileStorageError.
        """
        try:
            await upload_file_bytes(
                self._storage,
                bucket=self._bucket,
                key=storage_key,
                data=file_bytes,
                mime_type=upload.mime_type,
            )
        except Exception as exc:  # pragma: no cover - defensivo
            raise FileStorageError(
                f"No se pudo subir el archivo al storage: {exc}"
            ) from exc

        input_file, _, _ = await register_uploaded_input_file(
            session=self._db,
            upload=upload,
            uploaded_by=uploaded_by,
            storage_backend=self._backend,
            storage_path=storage_key,
            file_extension=None,
            checksum=checksum,
            parser_version=parser_version,
        )

        return InputFileResponse(
            input_file_id=input_file.input_file_id,
            file_id=input_file.file_id,
            project_id=input_file.project_id,
            uploaded_by=input_file.uploaded_by_auth_user_id,
            original_name=input_file.input_file_original_name,
            display_name=input_file.input_file_display_name,
            mime_type=input_file.input_file_mime_type,
            extension=input_file.input_file_extension,
            size_bytes=input_file.input_file_size_bytes,
            file_type=input_file.input_file_type,
            file_category=input_file.input_file_category,
            input_file_class=input_file.input_file_class,
            language=input_file.input_file_language,
            ingest_source=input_file.input_file_ingest_source,
            storage_backend=input_file.input_file_storage_backend,
            storage_path=input_file.input_file_storage_path,
            status=input_file.input_file_status,
            is_active=input_file.input_file_is_active,
            is_archived=input_file.input_file_is_archived,
            uploaded_at=input_file.input_file_uploaded_at,
        )

    # ------------------------------------------------------------------
    # Consultas y listados
    # ------------------------------------------------------------------
    async def list_project_input_files(
        self,
        *,
        project_id: UUID,
        include_archived: bool = False,
    ) -> list[InputFileResponse]:
        """
        Lista archivos insumo de un proyecto.

        Si `include_archived` es False, sólo devuelve archivos activos
        y no archivados.
        """
        items = await list_project_input_files(
            session=self._db,
            project_id=project_id,
            include_archived=include_archived,
        )

        return [
            InputFileResponse(
                input_file_id=inp.input_file_id,
                file_id=inp.file_id,
                project_id=inp.project_id,
                uploaded_by=inp.uploaded_by_auth_user_id,
                original_name=inp.input_file_original_name,
                display_name=inp.input_file_display_name,
                mime_type=inp.input_file_mime_type,
                extension=inp.input_file_extension,
                size_bytes=inp.input_file_size_bytes,
                file_type=inp.input_file_type,
                file_category=inp.input_file_category,
                input_file_class=inp.input_file_class,
                language=inp.input_file_language,
                ingest_source=inp.input_file_ingest_source,
                storage_backend=inp.input_file_storage_backend,
                storage_path=inp.input_file_storage_path,
                status=inp.input_file_status,
                is_active=inp.input_file_is_active,
                is_archived=inp.input_file_is_archived,
                uploaded_at=inp.input_file_uploaded_at,
            )
            for inp in items
        ]

    async def get_input_file_by_file_id(
        self,
        *,
        file_id: UUID,
    ) -> InputFileResponse:
        """
        Devuelve un InputFileResponse a partir de un `file_id` canónico.

        Lanza FileNotFoundError si no existe o no está vinculado a un input.
        """
        input_file = await get_input_file_by_file_id(
            session=self._db,
            file_id=file_id,
        )
        if input_file is None:
            raise FileNotFoundError("No se encontró un archivo insumo para ese file_id")

        return InputFileResponse(
            input_file_id=input_file.input_file_id,
            file_id=input_file.file_id,
            project_id=input_file.project_id,
            uploaded_by=input_file.uploaded_by_auth_user_id,
            original_name=input_file.input_file_original_name,
            display_name=input_file.input_file_display_name,
            mime_type=input_file.input_file_mime_type,
            extension=input_file.input_file_extension,
            size_bytes=input_file.input_file_size_bytes,
            file_type=input_file.input_file_type,
            file_category=input_file.input_file_category,
            input_file_class=input_file.input_file_class,
            language=input_file.input_file_language,
            ingest_source=input_file.input_file_ingest_source,
            storage_backend=input_file.input_file_storage_backend,
            storage_path=input_file.input_file_storage_path,
            status=input_file.input_file_status,
            is_active=input_file.input_file_is_active,
            is_archived=input_file.input_file_is_archived,
            uploaded_at=input_file.input_file_uploaded_at,
        )

    # ------------------------------------------------------------------
    # Descarga (URL firmada)
    # ------------------------------------------------------------------
    async def get_download_url_for_file(
        self,
        *,
        file_id: UUID,
        expires_in_seconds: int = 3600,
    ) -> str:
        """
        Genera una URL de descarga temporal para un archivo insumo.

        Lanza:
        - FileNotFoundError si no existe el archivo.
        - FileStorageError si el storage no puede generar la URL.
        """
        input_file = await get_input_file_by_file_id(
            session=self._db,
            file_id=file_id,
        )
        if input_file is None:
            raise FileNotFoundError("No se encontró un archivo insumo para ese file_id")

        storage_path = input_file.input_file_storage_path
        try:
            return await generate_download_url(
                self._storage,
                bucket=self._bucket,
                key=storage_path,
                expires_in_seconds=expires_in_seconds,
            )
        except Exception as exc:  # pragma: no cover - defensivo
            raise FileStorageError(
                f"No se pudo generar la URL de descarga: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Eliminación / archivado
    # ------------------------------------------------------------------
    async def delete_input_file(
        self,
        *,
        file_id: UUID,
        hard_delete: bool = False,
    ) -> None:
        """
        Elimina un archivo insumo.

        Si `hard_delete` es False (por defecto):
        - Marca el archivo como archivado (lógico) en BD.
        - El archivo puede conservarse en el storage (o borrarse según
          estrategia de retención futura).

        Si `hard_delete` es True:
        - Marca como archivado y desactiva.
        - Intenta eliminar el archivo del storage.

        NOTA:
        - Cualquier error de storage lanza FileStorageError.
        """
        input_file = await get_input_file_by_file_id(
            session=self._db,
            file_id=file_id,
        )
        if input_file is None:
            raise FileNotFoundError("No se encontró un archivo insumo para ese file_id")

        # 1) Archivado lógico
        await archive_input_file(
            session=self._db,
            input_file_id=input_file.input_file_id,
        )

        # 2) Borrado físico opcional
        if hard_delete:
            try:
                await delete_file_from_storage(
                    self._storage,
                    bucket=self._bucket,
                    key=input_file.input_file_storage_path,
                )
            except Exception as exc:  # pragma: no cover - defensivo
                raise FileStorageError(
                    f"No se pudo eliminar el archivo del storage: {exc}"
                ) from exc


__all__ = ["InputFilesFacade"]

# Fin del archivo backend/app/modules/files/facades/input_files/upload.py
