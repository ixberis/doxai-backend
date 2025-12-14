
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/product_files/__init__.py

Punto de entrada para servicios relacionados con archivos PRODUCTO (Files v2).

Expone funciones de alto nivel definidas en `service.py`.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from .service import (
    create_or_update_product_file,
    register_product_file_metadata,
    get_product_file,
    list_active_product_files,
    archive_product_file,
)

__all__ = [
    "create_or_update_product_file",
    "register_product_file_metadata",
    "get_product_file",
    "list_active_product_files",
    "archive_product_file",
]

# Fin del archivo backend/app/modules/files/services/product_files/__init__.py
