
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/__init__.py

Punto de agregación de fachadas del módulo Files (Files v2).

Actualmente expone:
- InputFilesFacade (clase) para archivos insumo.
- Funciones de fachada para archivos producto:
    - create_product_file
    - get_product_file_download_url
    - get_product_file_details
    - list_project_product_files
    - archive_product_file

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from .errors import (
    FilesError,
    FileNotFoundError,
    FileAccessDeniedError,
    FileStorageError,
    InvalidFileOperationError,
    InvalidFileType,
    FileValidationError,
)
from .input_files import InputFilesFacade
from .product_files import (
    create_product_file,
    get_product_file_download_url,
    get_product_file_details,
    list_project_product_files,
    archive_product_file,
)

__all__ = [
    # Errores de dominio
    "FilesError",
    "FileNotFoundError",
    "FileAccessDeniedError",
    "FileStorageError",
    "InvalidFileOperationError",
    "InvalidFileType",
    "FileValidationError",
    # Fachadas Input Files
    "InputFilesFacade",
    # Fachadas Product Files (funcionales)
    "create_product_file",
    "get_product_file_download_url",
    "get_product_file_details",
    "list_project_product_files",
    "archive_product_file",
]

# Fin del archivo backend/app/modules/files/facades/__init__.py