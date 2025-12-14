
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/product_files/__init__.py

Punto de entrada para las fachadas funcionales de archivos PRODUCTO.

Incluye:
- create_product_file
- get_product_file_download_url
- get_product_file_details
- list_project_product_files
- archive_product_file

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from .create import create_product_file
from .download import get_product_file_download_url
from .query import get_product_file_details, list_project_product_files
from .archive import archive_product_file

__all__ = [
    "create_product_file",
    "get_product_file_download_url",
    "get_product_file_details",
    "list_project_product_files",
    "archive_product_file",
]

# Fin del archivo backend/app/modules/files/facades/product_files/__init__.py