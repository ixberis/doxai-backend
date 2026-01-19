
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/bulk_download_service.py

Servicios para descargas masivas (bulk) de archivos, típicamente para generar
un ZIP a partir de varios archivos de un proyecto.

Responsabilidades:
- Validar que los archivos indicados en BulkDownloadRequest pertenezcan
  al proyecto indicado.
- Devolver un manifiesto básico con el estado de cada archivo.
- Delegar la generación efectiva del ZIP a otra capa (p. ej. zip_creator_service).

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.files.enums import FileRole
from app.modules.files.models.files_base_models import FilesBase
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.schemas.bulk_download_schemas import (
    BulkDownloadFileInfo,
    BulkDownloadRequest,
    BulkDownloadResponseItem,
)


async def _load_files_base_for_bulk(
    session: AsyncSession,
    project_id: UUID,
    file_infos: List[BulkDownloadFileInfo],
) -> dict[UUID, FilesBase]:
    """
    Carga FilesBase + hijos para un conjunto de file_ids y verifica que
    pertenecen al proyecto especificado.
    """
    file_ids = [fi.file_id for fi in file_infos]
    if not file_ids:
        return {}

    stmt = (
        select(FilesBase)
        .where(
            FilesBase.file_id.in_(file_ids),
            FilesBase.project_id == project_id,
        )
        .options(
            selectinload(FilesBase.input_file),
            selectinload(FilesBase.product_file),
        )
    )
    result = await session.execute(stmt)
    items = result.scalars().all()
    return {fb.file_id: fb for fb in items}


async def build_bulk_download_manifest(
    session: AsyncSession,
    request: BulkDownloadRequest,
) -> List[BulkDownloadResponseItem]:
    """
    Construye el manifiesto de archivos para una descarga masiva (ZIP).

    NOTA:
    - No realiza IO ni genera el ZIP; sólo resuelve qué archivos son válidos
      y con qué nombre deberían incluirse.
    - La capa de zip/descarga (zip_creator_service / storage) se encargará
      de consumir este manifiesto.
    """
    file_infos: list[BulkDownloadFileInfo] = list(request.files)
    fb_map = await _load_files_base_for_bulk(
        session=session,
        project_id=request.project_id,
        file_infos=file_infos,
    )

    manifest: list[BulkDownloadResponseItem] = []

    for info in file_infos:
        fb = fb_map.get(info.file_id)
        if fb is None:
            manifest.append(
                BulkDownloadResponseItem(
                    file_id=info.file_id,
                    file_name=info.file_name or str(info.file_id),
                    status="missing",
                    reason="file_id not found in files_base or does not belong to project",
                )
            )
            continue

        # Resolver nombre definitivo
        file_name = info.file_name or str(info.file_id)
        if fb.file_role == FileRole.INPUT and isinstance(fb.input_file, InputFile):
            file_name = (
                info.file_name
                or fb.input_file.input_file_display_name
                or fb.input_file.input_file_original_name
                or str(info.file_id)
            )
        elif (
            fb.file_role == FileRole.PRODUCT
            and isinstance(fb.product_file, ProductFile)
        ):
            file_name = (
                info.file_name
                or fb.product_file.product_file_display_name
                or fb.product_file.product_file_original_name
                or str(info.file_id)
            )

        manifest.append(
            BulkDownloadResponseItem(
                file_id=info.file_id,
                file_name=file_name,
                status="ok",
                reason=None,
            )
        )

    return manifest


class BulkDownloadService:
    """
    Clase wrapper para descargas masivas (compatibilidad con tests).
    """

    def __init__(self, db: AsyncSession, storage, project_service):
        self.db = db
        self.storage = storage
        self.project_service = project_service

    async def create_bulk_download(
        self,
        project_id: UUID,
        user_id: str,
        category = None,
    ) -> bytes:
        """
        Crea un ZIP con archivos del proyecto.
        """
        import io
        import zipfile
        from app.modules.files.enums import FileCategory

        # Validar acceso
        await self.project_service.validate_user_access(project_id, user_id)

        # Recolectar archivos
        files_data = {}

        # Input files
        if category is None or category == FileCategory.input:
            stmt = select(InputFile).where(
                InputFile.project_id == project_id,
                InputFile.input_file_is_active == True,
                InputFile.input_file_is_archived == False,
            )
            result = await self.db.execute(stmt)
            input_files = result.scalars().all()

            for f in input_files:
                try:
                    data = await self.storage.download(f.input_file_storage_path)
                    zip_path = f"input/{f.input_file_display_name}"
                    files_data[zip_path] = data
                except FileNotFoundError:
                    # Skip missing files
                    continue

        # Product files
        if category is None or category == FileCategory.product_files:
            stmt = select(ProductFile).where(
                ProductFile.project_id == project_id,
                ProductFile.product_file_is_active == True,
                ProductFile.product_file_is_archived == False,
            )
            result = await self.db.execute(stmt)
            product_files = result.scalars().all()

            for f in product_files:
                try:
                    data = await self.storage.download(f.product_file_storage_path)
                    zip_path = f"output/{f.product_file_display_name}"
                    files_data[zip_path] = data
                except FileNotFoundError:
                    # Skip missing files
                    continue

        # Crear ZIP
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, content in files_data.items():
                zf.writestr(name, content)

        return buffer.getvalue()


__all__ = ["build_bulk_download_manifest", "BulkDownloadService"]

# Fin del archivo backend/app/modules/files/services/bulk_download_service.py





