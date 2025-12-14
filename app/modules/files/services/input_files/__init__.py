
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/input_files/__init__.py

Punto de entrada para servicios relacionados con archivos INSUMO (Files v2).

Expone funciones de alto nivel definidas en `service.py`.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from .service import (
    register_uploaded_input_file,
    get_input_file,
    list_project_input_files,
    archive_input_file,
    unarchive_input_file,
)

__all__ = [
    "register_uploaded_input_file",
    "get_input_file",
    "list_project_input_files",
    "archive_input_file",
    "unarchive_input_file",
]

# Fin del archivo backend/app/modules/files/services/input_files/__init__.py
