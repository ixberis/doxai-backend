
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/file_category_enum.py

Categoría de archivos en DoxAI:

- input  : archivo insumo, subido por la persona usuaria para alimentar el funnel RAG
- product: archivo producto, generado por el sistema (salida del modelo RAG)

Notas:
- Los valores **canónicos** son 'input' y 'product' (minúsculas).
- Se mantienen aliases de compatibilidad: 'output' → 'product', variantes en plural,
  mayúsculas, y equivalentes en español ('insumo(s)', 'producto(s)').
- _missing_ normaliza entradas de texto legacy a los valores canónicos.

Autor: Ixchel Beristáin
Fecha: 29/10/2025
"""

from __future__ import annotations

from typing import Any
from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from .compat_base import _StrEnum, EnumMixin


# Valores canónicos para PostgreSQL
_FILE_CATEGORY_VALUES = ["input", "product"]


class FileCategory(EnumMixin, _StrEnum):
    # --- Valores canónicos ---
    input = "input"
    product = "product"

    # --- Aliases de compatibilidad (inglés y español, sing./plur., mayúsculas) ---
    # Input
    input_file = input
    input_files = input
    INPUT = input
    INPUT_FILE = input
    INPUT_FILES = input
    insumo = input
    insumos = input

    # Product (antes "output")
    product_file = product
    product_files = product
    PRODUCT = product
    PRODUCT_FILE = product
    PRODUCT_FILES = product
    output = product
    outputs = product
    OUTPUT = product
    OUTPUTS = product
    producto = product
    productos = product

    # --- Compat layer: mapea strings legacy/sinónimos a los canónicos ---
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            v = value.strip().lower()
            mapping = {
                # input
                "input": "input",
                "input_file": "input",
                "input_files": "input",
                "insumo": "input",
                "insumos": "input",
                # product / output
                "product": "product",
                "product_file": "product",
                "product_files": "product",
                "output": "product",
                "outputs": "product",
                "producto": "product",
                "productos": "product",
            }
            if v in mapping:
                return getattr(cls, mapping[v])
        raise ValueError(f"{value!r} is not a valid {cls.__name__}")


class FileCategoryType(TypeDecorator):
    """
    TypeDecorator que mapea FileCategory ↔ PostgreSQL file_category_enum.
    """
    impl = PG_ENUM(
        *_FILE_CATEGORY_VALUES,
        name="file_category_enum",
        create_type=False,
    )
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, FileCategory):
            return value.value
        if isinstance(value, str):
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return FileCategory(value)


def as_pg_enum() -> FileCategoryType:
    """
    Devuelve el tipo SQLAlchemy TypeDecorator para file_category_enum.
    """
    return FileCategoryType()


# Alias para compatibilidad
file_category_as_pg_enum = as_pg_enum


__all__ = ["FileCategory", "FileCategoryType", "as_pg_enum", "file_category_as_pg_enum"]
# Fin del archivo


