# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/product_version_enum.py

Enum de versiones de "product files".
Versión del "contrato" de producto.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from .compat_base import _StrEnum, EnumMixin


class ProductVersion(EnumMixin, _StrEnum):
    v1 = "v1"
    # Agrega v2, v3, etc. según evolucione tu dominio
    
    # Aliases legacy
    V1 = v1
    PRODUCT_V1 = v1


PG_TYPE_NAME = "product_version_enum"

def as_pg_enum(name: str = PG_TYPE_NAME, native_enum: bool = False) -> PG_ENUM:
    """
    Devuelve un Enum de SQLAlchemy ligado a ProductVersion.
    """
    return PG_ENUM(
        ProductVersion,
        name=name,
        create_type=False,
        values_callable=lambda x: [e.value for e in x]
    )


__all__ = ["ProductVersion", "as_pg_enum"]

