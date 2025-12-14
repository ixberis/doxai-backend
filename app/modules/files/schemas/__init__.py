
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/schemas/__init__.py

Punto de agregación de schemas Pydantic del módulo Files (versión 2).

Expone:
- Schemas de archivos insumo.
- Schemas de metadatos de insumo.
- Schemas de archivos producto.
- Schemas de metadatos de producto.
- Schemas de descarga selectiva y masiva.

Autor: DoxAI / Ajustes Files v2 por Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from .input_file_schemas import (
    InputFileUpload,
    InputFileUpdate,
    InputFileResponse,
    InputFileCreate,
)

from .input_file_metadata_schemas import (
    InputFileMetadataCreate,
    InputFileMetadataResponse,
    InputFileMetadataUpdate,
)

from .product_file_schemas import (
    ProductFileCreate,
    ProductFileResponse,
    ProjectFileUnionResponse,
)

from .product_file_metadata_schemas import (
    ProductFileMetadataCreate,
    ProductFileMetadataRead,
    ProductFileReviewUpdate,
)

from .selected_download_schemas import (
    SelectedFilesDownloadRequest,
    PartialDownloadResponse,
    PartialDownloadResponseItem,
)

from .bulk_download_schemas import (
    BulkDownloadFileInfo,
    BulkDownloadRequest,
    BulkDownloadResponseItem,
)


__all__ = [
    # Input file schemas
    "InputFileUpload",
    "InputFileUpdate",
    "InputFileResponse",
    "InputFileCreate",
    "InputFileMetadataCreate",
    "InputFileMetadataResponse",
    "InputFileMetadataUpdate",
    # Product file schemas
    "ProductFileCreate",
    "ProductFileResponse",
    "ProjectFileUnionResponse",
    "ProductFileMetadataCreate",
    "ProductFileMetadataRead",
    "ProductFileReviewUpdate",
    # Selected download schemas
    "SelectedFilesDownloadRequest",
    "PartialDownloadResponse",
    "PartialDownloadResponseItem",
    # Bulk download schemas
    "BulkDownloadFileInfo",
    "BulkDownloadRequest",
    "BulkDownloadResponseItem",
]

# Fin del archivo backend/app/modules/files/schemas/__init__.py