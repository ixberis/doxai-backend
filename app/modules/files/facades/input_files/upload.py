
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
from app.modules.files.repositories import input_file_repository
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
        input_file_id: Optional[UUID] = None,
        checksum: Optional[str] = None,
        parser_version: Optional[str] = None,
    ) -> InputFileResponse:
        """
        Sube un archivo insumo al storage y registra sus metadatos en BD.

        Flujo:
        1. Sube `file_bytes` a storage usando (bucket_name, storage_key).
        2. Crea InputFile + FilesBase + (opcional) InputFileMetadata.
        3. Devuelve un InputFileResponse listo para API.

        Args:
            input_file_id: UUID pre-generado para SSOT path. Si no se pasa,
                          se genera uno nuevo en el servicio.

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
            input_file_id=input_file_id,
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
        
        Incluye campo calculado `storage_exists` que indica si el archivo
        existe físicamente en storage.objects (detección de fantasmas).
        
        Degradación segura:
        - Si storage.objects no es accesible, storage_exists = None (unknown)
        - El frontend debe tratar None como "desconocido", permitiendo selección
        """
        import logging
        from sqlalchemy import text, bindparam
        
        _logger = logging.getLogger("files.list.storage_check")
        
        items = await list_project_input_files(
            session=self._db,
            project_id=project_id,
            include_archived=include_archived,
        )
        
        # Obtener paths existentes en storage.objects para este bucket
        # Query eficiente: batch check solo sobre items de esta página
        storage_paths: set[str] | None = None  # None = unknown/error
        storage_check_failed = False
        
        if items:
            all_paths = [inp.input_file_storage_path for inp in items if inp.input_file_storage_path]
            if all_paths:
                try:
                    # SQL robusto asyncpg: usar IN :paths con bindparam(expanding=True)
                    storage_check_sql = text("""
                        SELECT name 
                        FROM storage.objects 
                        WHERE bucket_id = :bucket 
                        AND name IN :paths
                    """).bindparams(
                        bindparam("bucket"),
                        bindparam("paths", expanding=True)
                    )
                    result = await self._db.execute(
                        storage_check_sql,
                        {"bucket": self._bucket, "paths": all_paths}
                    )
                    storage_paths = {row[0] for row in result.fetchall()}
                except Exception as e:
                    # Degradación segura: log error, marcar como unknown
                    storage_check_failed = True
                    _logger.error(
                        "storage_objects_check_failed: project=%s bucket=%s error=%s paths_count=%d",
                        str(project_id)[:8],
                        self._bucket,
                        str(e)[:200],
                        len(all_paths),
                    )
        
        def _compute_storage_exists(path: str | None) -> bool | None:
            """Compute storage_exists with safe degradation."""
            if storage_check_failed or storage_paths is None:
                return None  # Unknown - storage check failed
            if not path:
                return None  # No path recorded
            return path in storage_paths

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
                storage_exists=_compute_storage_exists(inp.input_file_storage_path),
            )
            for inp in items
        ]

    async def get_input_file_by_file_id(
        self,
        *,
        file_id: UUID,
        include_inactive: bool = False,
    ) -> InputFileResponse:
        """
        Devuelve un InputFileResponse a partir de un `file_id` canónico.

        Args:
            file_id: ID canónico del archivo (files_base).
            include_inactive: Si True, incluye archivos invalidados/inactivos.
                              Útil para operaciones idempotentes como DELETE.

        Lanza FileNotFoundError si no existe o no está vinculado a un input.
        """
        input_file = await get_input_file_by_file_id(
            session=self._db,
            file_id=file_id,
        )
        if input_file is None:
            raise FileNotFoundError("No se encontró un archivo insumo para ese file_id")
        
        # Si no incluye inactivos y está inactivo, lanzar 404
        if not include_inactive and not input_file.input_file_is_active:
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
        delete_from_storage: bool = True,
    ) -> tuple[UUID | None, int]:
        """
        Elimina un archivo insumo (invalidación lógica + storage idempotente).

        Comportamiento:
        - Invalida lógicamente el registro en BD (storage_state='missing', is_active=False).
        - Si `delete_from_storage=True`, elimina el archivo físico del storage (best-effort).
        - Siempre preserva el registro en BD para histórico/auditoría.

        IDEMPOTENCIA:
        - Si el archivo ya está invalidado (storage_state != 'present' o is_active=false),
          retorna sin error (204 implícito).
        - Si el archivo no existe en storage, se trata como éxito.
        - Cualquier otro error de storage lanza FileStorageError.

        Args:
            file_id: UUID del archivo (files_base.file_id).
            delete_from_storage: Si True (default), elimina el archivo físico del storage.

        Returns:
            tuple[project_id, db_ops_count]: El project_id del archivo (para touch) y
            el número de operaciones DB realizadas.
        """
        import logging
        from app.modules.files.enums import FileStorageState
        
        _logger = logging.getLogger("files.delete")
        db_ops_count = 0
        
        # Lookup sin filtros de estado (incluye inactivos/missing)
        input_file = await get_input_file_by_file_id(
            session=self._db,
            file_id=file_id,
        )
        db_ops_count += 1
        
        if input_file is None:
            raise FileNotFoundError("No se encontró un archivo insumo para ese file_id")

        project_id = input_file.project_id

        # --- IDEMPOTENCIA: si ya está invalidado, retornar early ---
        from app.modules.files.utils.enum_helpers import safe_enum_value
        
        state_str = safe_enum_value(input_file.storage_state)
        already_invalidated = (state_str != FileStorageState.present.value) or (not input_file.input_file_is_active)
        
        if already_invalidated:
            _logger.info(
                "delete_idempotent_already_missing: file_id=%s input_file_id=%s storage_state=%s is_active=%s db_ops=%d",
                str(file_id)[:8],
                str(input_file.input_file_id)[:8],
                state_str,
                input_file.input_file_is_active,
                db_ops_count,
            )
            return (project_id, db_ops_count)  # Éxito idempotente, nada que hacer

        if delete_from_storage:
            # 1) Eliminar del storage (idempotente si no existe)
            storage_path = input_file.input_file_storage_path
            try:
                await delete_file_from_storage(
                    self._storage,
                    bucket=self._bucket,
                    key=storage_path,
                )
                _logger.info(
                    "storage_delete_ok: bucket=%s path=%s",
                    self._bucket,
                    storage_path[:60] if storage_path else "<none>",
                )
            except Exception as exc:
                error_str = str(exc).lower()
                # Tratar "not found" como idempotente
                if "not found" in error_str or "404" in error_str or "does not exist" in error_str:
                    _logger.info(
                        "storage_delete_idempotent: bucket=%s path=%s (already deleted or never existed)",
                        self._bucket,
                        storage_path[:60] if storage_path else "<none>",
                    )
                else:
                    raise FileStorageError(
                        f"No se pudo eliminar el archivo del storage: {exc}"
                    ) from exc
            
            # Invalidación lógica en BD (siempre preserva histórico)
            invalidated = await input_file_repository.invalidate_for_deletion(
                session=self._db,
                input_file_id=input_file.input_file_id,
                reason="user_deleted",
            )
            db_ops_count += 1
            
            if invalidated:
                _logger.info(
                    "db_logical_invalidation_ok: input_file_id=%s storage_state=missing db_ops=%d tx_mode=single_tx",
                    str(input_file.input_file_id)[:8],
                    db_ops_count,
                )
        else:
            # Modo legacy: solo archivado lógico
            await archive_input_file(
                session=self._db,
                input_file_id=input_file.input_file_id,
            )
            db_ops_count += 1
        
        return (project_id, db_ops_count)


__all__ = ["InputFilesFacade"]

# Fin del archivo backend/app/modules/files/facades/input_files/upload.py
