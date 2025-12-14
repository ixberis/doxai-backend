# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/ingest_source_enum.py

Enum de fuentes de ingesta de archivos en DoxAI.
Trazabilidad del origen del archivo para auditoría y lógica de negocio.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-25
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy import TypeDecorator

from .compat_base import _StrEnum, EnumMixin


class IngestSource(EnumMixin, _StrEnum):
    """
    Fuente de ingesta del archivo al sistema.
    
    Valores:
        upload: Carga directa por usuario (UI o API)
        url: Descarga desde URL externa
        email: Recibido por correo electrónico
        api: Ingesta programática desde API externa
        batch: Carga batch/masiva (migraciones, scripts)
    """
    upload = "upload"
    url = "url"
    email = "email"
    api = "api"
    batch = "batch"
    
    # Aliases legacy
    UPLOAD = upload
    URL = url
    EMAIL = email
    API = api
    BATCH = batch


# Valores canónicos para PostgreSQL
_INGEST_SOURCE_VALUES = ["upload", "url", "email", "api", "batch"]


class IngestSourceType(TypeDecorator):
    """
    TypeDecorator para mapear IngestSource a ingest_source_enum de PostgreSQL.
    """
    impl = PG_ENUM(*_INGEST_SOURCE_VALUES, name="ingest_source_enum", create_type=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, IngestSource):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return IngestSource(value)


def as_pg_enum(name: str = "ingest_source_enum", native_enum: bool = False) -> IngestSourceType:
    """
    Devuelve un TypeDecorator ligado a IngestSource.
    """
    return IngestSourceType()


__all__ = ["IngestSource", "IngestSourceType", "as_pg_enum"]
