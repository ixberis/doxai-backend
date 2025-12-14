# -*- coding: utf-8 -*-
"""
backend/app/modules/files/models/__init__.py

Modelos ORM del módulo de archivos.

Autor: Ixchel Beristáin
Fecha: 26/10/2025
"""

from .input_file_models import InputFile
from .input_file_metadata_models import InputFileMetadata
from .product_file_models import ProductFile
from .product_file_metadata_models import ProductFileMetadata
from .product_file_activity_models import ProductFileActivity

__all__ = [
    "InputFile",
    "InputFileMetadata",
    "ProductFile",
    "ProductFileMetadata",
    "ProductFileActivity",
]
