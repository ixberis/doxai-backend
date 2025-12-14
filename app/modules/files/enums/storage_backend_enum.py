# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/storage_backend_enum.py

Enum de backends de almacenamiento en DoxAI.
Permite desacoplar la capa de almacenamiento físico.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-25
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy import TypeDecorator

from .compat_base import _StrEnum, EnumMixin


class StorageBackend(EnumMixin, _StrEnum):
    """
    Backend de almacenamiento de archivos.
    
    Valores:
        supabase: Supabase Storage (principal para DoxAI)
        local: Almacenamiento en filesystem local
        s3: Amazon S3 o compatible (MinIO, etc)
        gcs: Google Cloud Storage
        azure: Azure Blob Storage
    """
    supabase = "supabase"
    local = "local"
    s3 = "s3"
    gcs = "gcs"
    azure = "azure"
    
    # Aliases legacy
    SUPABASE = supabase
    LOCAL = local
    S3 = s3
    GCS = gcs
    AZURE = azure


# Valores canónicos para PostgreSQL
_STORAGE_BACKEND_VALUES = ["supabase", "local", "s3", "gcs", "azure"]


class StorageBackendType(TypeDecorator):
    """
    TypeDecorator para mapear StorageBackend a storage_backend_enum de PostgreSQL.
    """
    impl = PG_ENUM(*_STORAGE_BACKEND_VALUES, name="storage_backend_enum", create_type=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, StorageBackend):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return StorageBackend(value)


def as_pg_enum(name: str = "storage_backend_enum", native_enum: bool = False) -> StorageBackendType:
    """
    Devuelve un TypeDecorator ligado a StorageBackend.
    """
    return StorageBackendType()


__all__ = ["StorageBackend", "StorageBackendType", "as_pg_enum"]
