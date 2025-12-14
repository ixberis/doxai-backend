
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/product_file_activity/__init__.py

Punto de entrada para servicios relacionados con la actividad de
archivos PRODUCTO (Files v2).

Expone funciones de alto nivel definidas en `service.py`.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from .service import (
    log_product_file_event,
    list_activity_for_product_file,
    list_activity_for_project,
)

__all__ = [
    "log_product_file_event",
    "list_activity_for_product_file",
    "list_activity_for_project",
]

# Fin del archivo backend/app/modules/files/services/product_file_activity/__init__.py
