
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/repositories/__init__.py

Punto de agregación de repositorios async del módulo Files (Files v2).

Incluye repos para:
- files_base
- input_files
- input_file_metadata
- product_files
- product_file_metadata
- product_file_activity

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from . import files_base_repository
from . import input_file_repository
from . import input_file_metadata_repository
from . import product_file_repository
from . import product_file_metadata_repository
from . import product_file_activity_repository

__all__ = [
    "files_base_repository",
    "input_file_repository",
    "input_file_metadata_repository",
    "product_file_repository",
    "product_file_metadata_repository",
    "product_file_activity_repository",
]

# Fin del archivo backend/app/modules/files/repositories/__init__.py