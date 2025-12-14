# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/input_file_class_enum.py

Enum de clase/tipo de archivo de entrada para DoxAI.
Catch-all de insumos; expandir con clases específicas según dominio.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from .compat_base import _StrEnum, EnumMixin


class InputFileClass(EnumMixin, _StrEnum):
    """
    Clase lógica de archivo de entrada.

    Por ahora mantenemos un set mínimo alineado con los tests.
    Se puede ampliar (p. ej. 'annex', 'support', etc.) sin romper compatibilidad.
    """

    # Clase principal: insumo fuente del proyecto
    source = "source"

    # Algunas clases adicionales razonables (por si las usamos después)
    annex = "annex"
    reference = "reference"
    other = "other"

    # Aliases legacy/convención en MAYÚSCULAS
    SOURCE = source
    ANNEX = annex
    REFERENCE = reference
    OTHER = other


def as_pg_enum(name: str = "input_file_class_enum") -> PG_ENUM:
    """
    Devuelve un Enum de SQLAlchemy ligado a InputFileClass.

    Args:
        name: nombre del tipo en PostgreSQL.

    Returns:
        sqlalchemy.Enum configurado con InputFileClass.
    """
    return PG_ENUM(
        InputFileClass,
        name=name,
        create_type=False,
        values_callable=lambda x: [e.value for e in x],
    )


__all__ = ["InputFileClass", "as_pg_enum"]
