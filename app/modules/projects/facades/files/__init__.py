# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/files/__init__.py

Re-exporta operaciones de archivos de proyecto.

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

from .ops import (
    add_file,
    mark_validated,
    move_file,
    delete_file,
)

__all__ = [
    "add_file",
    "mark_validated",
    "move_file",
    "delete_file",
]
