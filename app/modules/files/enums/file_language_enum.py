# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/file_language_enum.py

Enum de idiomas de archivo en DoxAI.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy import TypeDecorator

from .compat_base import _StrEnum, EnumMixin


class FileLanguage(EnumMixin, _StrEnum):
    es = "es"
    en = "en"
    fr = "fr"
    de = "de"
    pt = "pt"
    it = "it"
    und = "und"  # undefined/unknown
    
    # Aliases legacy
    ES = es
    EN = en
    FR = fr
    DE = de
    PT = pt
    IT = it
    UND = und


# Valores canónicos (sin aliases) para PostgreSQL
_FILE_LANGUAGE_VALUES = ["es", "en", "pt", "fr", "de", "it", "und"]


class FileLanguageType(TypeDecorator):
    """
    TypeDecorator que convierte FileLanguage enum a string para PostgreSQL.
    Resuelve el problema de StrEnum con aliases que SQLAlchemy no maneja correctamente.
    """
    impl = PG_ENUM(*_FILE_LANGUAGE_VALUES, name="file_language_enum", create_type=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, FileLanguage):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return FileLanguage(value)


def as_pg_enum(name: str = "file_language_enum", native_enum: bool = False) -> FileLanguageType:
    """
    Devuelve el TypeDecorator para FileLanguage.
    """
    return FileLanguageType()


# --- Compatibility alias ---
Language = FileLanguage

__all__ = ["FileLanguage", "FileLanguageType", "Language", "as_pg_enum"]
