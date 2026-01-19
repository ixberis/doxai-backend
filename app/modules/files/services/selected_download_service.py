
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/selected_download_service.py

Servicios para construir el manifiesto de descargas selectivas de archivos.

Responsabilidades:
- A partir de una lista de file_ids canónicos, validar qué archivos existen.
- Resolver nombre de archivo y ruta de storage (input/product).
- Construir un resumen de éxito/fallo por archivo (PartialDownloadResponse).

NOTA:
- Esta capa NO genera URLs ni ZIPs. Eso se delega a servicios de storage.
- Facades/ruteadores pueden usar este manifiesto para construir:
    - respuestas JSON
    - tareas asíncronas de empaquetado
    - URLs firmadas, etc.

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
from app.modules.files.schemas.selected_download_schemas import (
    SelectedFilesDownloadRequest,
    PartialDownloadResponse,
    PartialDownloadResponseItem,
)


async def _load_files_base_with_children(
    session: AsyncSession,
    file_ids: List[UUID],
) -> dict[UUID, FilesBase]:
    """
    Carga FilesBase + InputFile/ProductFile para una lista de file_ids.
    """
    if not file_ids:
        return {}

    stmt = (
        select(FilesBase)
        .where(FilesBase.file_id.in_(file_ids))
        .options(
            selectinload(FilesBase.input_file),
            selectinload(FilesBase.product_file),
        )
    )
    result = await session.execute(stmt)
    items = result.scalars().all()
    return {fb.file_id: fb for fb in items}


async def build_selected_download_manifest(
    session: AsyncSession,
    request: SelectedFilesDownloadRequest,
) -> PartialDownloadResponse:
    """
    Construye el manifiesto de descarga selectiva para los file_ids solicitados.

    No realiza operaciones de IO ni de storage; únicamente:
    - Verifica qué file_ids existen en files_base.
    - Determina nombre de archivo más apropiado para cada uno.
    - Marca como missing aquellos que no se encuentran.

    La lógica específica de generación de ZIP/URLs se implementa en la capa
    de storage o en una fachada superior.
    """
    file_ids = list(request.file_ids)
    fb_map = await _load_files_base_with_children(session, file_ids)

    downloaded: list[PartialDownloadResponseItem] = []
    missing: list[PartialDownloadResponseItem] = []

    for fid in file_ids:
        fb = fb_map.get(fid)
        if fb is None:
            missing.append(
                PartialDownloadResponseItem(
                    file_id=fid,
                    file_name=str(fid),
                    status="missing",
                    reason="file_id not found in files_base",
                )
            )
            continue

        # Resolver archivo asociado según file_role (SSOT)
        file_name: str = str(fid)
        if fb.file_role == FileRole.INPUT and isinstance(fb.input_file, InputFile):
            file_name = (
                fb.input_file.input_file_display_name
                or fb.input_file.input_file_original_name
                or str(fid)
            )
        elif (
            fb.file_role == FileRole.PRODUCT
            and isinstance(fb.product_file, ProductFile)
        ):
            file_name = (
                fb.product_file.product_file_display_name
                or fb.product_file.product_file_original_name
                or str(fid)
            )

        downloaded.append(
            PartialDownloadResponseItem(
                file_id=fid,
                file_name=file_name,
                status="ok",
                reason=None,
            )
        )

    total_requested = len(file_ids)
    success_count = len(downloaded)
    missing_count = len(missing)

    return PartialDownloadResponse(
        downloaded=downloaded,
        missing=missing,
        total_requested=total_requested,
        success_count=success_count,
        missing_count=missing_count,
    )


class SelectedDownloadService:
    """
    Clase wrapper para descargas selectivas (compatibilidad con tests).
    """

    def __init__(self, db: AsyncSession, project_service):
        self.db = db
        self.project_service = project_service

    async def prepare_selected_download(
        self,
        project_id: UUID,
        user_id: str,
        file_ids: List[UUID],
    ) -> dict:
        """
        Prepara un manifiesto de descarga para archivos seleccionados.
        """
        from app.modules.files.enums import FileCategory

        # Validar acceso
        await self.project_service.validate_user_access(project_id, user_id)

        files = []

        # Buscar input files
        stmt = select(InputFile).where(
            InputFile.input_file_id.in_(file_ids),
            InputFile.project_id == project_id,
            InputFile.input_file_is_active == True,
            InputFile.input_file_is_archived == False,
        )
        result = await self.db.execute(stmt)
        input_files = result.scalars().all()

        for f in input_files:
            files.append({
                "storage_path": f.input_file_storage_path,
                "size_bytes": f.input_file_size_bytes,
                "category": FileCategory.input,
                "display_name": f.input_file_display_name,
            })

        # Buscar product files
        stmt = select(ProductFile).where(
            ProductFile.product_file_id.in_(file_ids),
            ProductFile.project_id == project_id,
            ProductFile.product_file_is_active == True,
            ProductFile.product_file_is_archived == False,
        )
        result = await self.db.execute(stmt)
        product_files = result.scalars().all()

        for f in product_files:
            files.append({
                "storage_path": f.product_file_storage_path,
                "size_bytes": f.product_file_size_bytes,
                "category": FileCategory.product,
                "display_name": f.product_file_display_name,
            })

        return {
            "project_id": project_id,
            "files": files,
        }


__all__ = ["build_selected_download_manifest", "SelectedDownloadService"]

# Fin del archivo backend/app/modules/files/services/selected_download_service.py
