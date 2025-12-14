# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/product_file_generation_method_enum.py

Enum del método de generación de los product files.
Trazabilidad del origen: convertidor, manual o RAG.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from .compat_base import _StrEnum, EnumMixin


class GenerationMethod(EnumMixin, _StrEnum):
    converter = "converter"
    manual    = "manual"
    rag       = "rag"
    hybrid    = "hybrid"
    
    # Aliases legacy
    CONVERTER = converter
    MANUAL = manual
    RAG = rag
    HYBRID = hybrid


PG_TYPE_NAME = "product_file_generation_method_enum"

def as_pg_enum(name: str = PG_TYPE_NAME) -> PG_ENUM:
    """
    Devuelve un Enum de SQLAlchemy ligado a GenerationMethod.
    """
    return PG_ENUM(
        GenerationMethod,
        name=name,
        create_type=False,
        values_callable=lambda x: [e.value for e in x]
    )


__all__ = ["GenerationMethod", "as_pg_enum"]

