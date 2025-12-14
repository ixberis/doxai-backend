
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/schemas/bulk_download_schemas.py

Schemas Pydantic v2 para descarga masiva de archivos (ZIP).

Incluye:
- BulkDownloadFileInfo: descripción de un archivo incluido en un ZIP.
- BulkDownloadRequest: criterios de descarga masiva.
- BulkDownloadResponseItem: entrada del manifiesto de archivos generados.

Autor: DoxAI / Ajustes Files v2 por Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.files.enums import FileType, FileCategory


class BulkDownloadFileInfo(BaseModel):
    """
    Información básica de un archivo a incluir en descarga masiva.
    """

    file_id: UUID = Field(..., description="ID canónico del archivo en files_base")
    file_name: str = Field(..., description="Nombre con el que se incluirá en el ZIP")
    file_type: Optional[FileType] = Field(
        default=None,
        description="Tipo lógico del archivo, si se desea filtrar o etiquetar",
    )
    file_category: Optional[FileCategory] = Field(
        default=None,
        description="Categoría del archivo (input/product), si aplica",
    )


class BulkDownloadRequest(BaseModel):
    """
    Solicitud de descarga masiva (ZIP) de archivos.
    """

    project_id: UUID = Field(..., description="Proyecto al que pertenecen los archivos")
    category: Optional[FileCategory] = Field(
        default=None,
        description="Categoría de archivos a incluir (input_files/product_files)",
    )
    file_types: Optional[List[FileType]] = Field(
        default=None,
        description="Tipos de archivos a filtrar",
    )
    files: Optional[List[BulkDownloadFileInfo]] = Field(
        default=None,
        description="Lista explícita de archivos a empaquetar en el ZIP",
    )
    zip_name: Optional[str] = Field(
        default=None,
        description="Nombre sugerido para el archivo ZIP resultante",
    )


class BulkDownloadResponseItem(BaseModel):
    """
    Entrada del manifiesto de archivos generados para descarga masiva.
    """

    model_config = ConfigDict(from_attributes=True)

    file_id: UUID = Field(..., description="ID canónico del archivo")
    file_name: str = Field(..., description="Nombre del archivo dentro del ZIP")
    status: str = Field(..., description="Estado (ok/missing/error)")
    reason: Optional[str] = Field(
        default=None,
        description="Detalle del error si el archivo no se pudo incluir",
    )


__all__ = [
    "BulkDownloadFileInfo",
    "BulkDownloadRequest",
    "BulkDownloadResponseItem",
]

# Fin del archivo backend/app/modules/files/schemas/bulk_download_schemas.py


