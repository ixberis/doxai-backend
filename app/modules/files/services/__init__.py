
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/__init__.py

Punto de agregación de servicios de dominio del módulo Files (Files v2).

Actualmente expone:
- Servicios de archivos insumo.
- Servicios de archivos producto.
- Servicios de actividad de archivos producto.
- Servicios de búsqueda de archivos.
- Servicios para descargas selectivas y masivas.

Otros servicios (analytics, cache, storage, checksums) se tratarán como
capas de infraestructura y se irán adaptando gradualmente en fases
posteriores (métricas/observabilidad, etc.).

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Input files
# ---------------------------------------------------------------------------
from .input_files import (
    register_uploaded_input_file,
    get_input_file,
    list_project_input_files,
    archive_input_file,
    unarchive_input_file,
)

# ---------------------------------------------------------------------------
# Product files
# ---------------------------------------------------------------------------
from .product_files import (
    create_or_update_product_file,
    register_product_file_metadata,
    get_product_file,
    list_active_product_files,
    archive_product_file,
)

# ---------------------------------------------------------------------------
# Product file activity
# ---------------------------------------------------------------------------
from .product_file_activity import (
    log_product_file_event,
    list_activity_for_product_file,
    list_activity_for_project,
)

# ---------------------------------------------------------------------------
# Search & downloads (Files v2)
# ---------------------------------------------------------------------------
from .files_search_service import search_project_files
from .selected_download_service import build_selected_download_manifest
from .bulk_download_service import build_bulk_download_manifest

__all__ = [
    # Input files
    "register_uploaded_input_file",
    "get_input_file",
    "list_project_input_files",
    "archive_input_file",
    "unarchive_input_file",
    # Product files
    "create_or_update_product_file",
    "register_product_file_metadata",
    "get_product_file",
    "list_active_product_files",
    "archive_product_file",
    # Product file activity
    "log_product_file_event",
    "list_activity_for_product_file",
    "list_activity_for_project",
    # Search & downloads
    "search_project_files",
    "build_selected_download_manifest",
    "build_bulk_download_manifest",
]

# Fin del archivo backend/app/modules/files/services/__init__.py







