# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/product_file_event_enum.py

Enum de eventos de auditoría para archivos de producto en DoxAI.
Valores en minúsculas con aliases legacy en MAYÚSCULAS.

Autor: Ixchel Beristáin
Fecha: 2025-10-23
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from .compat_base import _StrEnum, EnumMixin


class ProductFileEvent(EnumMixin, _StrEnum):
    # Product file events
    generated  = "generated"
    downloaded = "downloaded"
    exported   = "exported"
    updated    = "updated"
    archived   = "archived"
    deleted    = "deleted"
    
    # Input file processing events (compatible con InputFileActivity)
    uploaded   = "uploaded"
    queued     = "queued"
    processing = "processing"
    parsed     = "parsed"
    completed  = "completed"
    vectorized = "vectorized"
    failed     = "failed"
    
    # Aliases legacy en minúsculas
    GENERATED = generated
    DOWNLOADED = downloaded
    EXPORTED = exported
    UPDATED = updated
    ARCHIVED = archived
    DELETED = deleted
    UPLOADED = uploaded
    QUEUED = queued
    PROCESSING = processing
    PARSED = parsed
    COMPLETED = completed
    VECTORIZED = vectorized
    FAILED = failed
    
    # Aliases en MAYÚSCULAS para tests
    PRODUCT_FILE_GENERATED = "generated"
    PRODUCT_FILE_DOWNLOADED = "downloaded"
    PRODUCT_FILE_EXPORTED = "exported"
    PRODUCT_FILE_UPDATED = "updated"
    PRODUCT_FILE_ARCHIVED = "archived"


PG_TYPE_NAME = "product_file_event_enum"

def as_pg_enum(name: str = PG_TYPE_NAME) -> PG_ENUM:
    """
    Devuelve un Enum de SQLAlchemy ligado a ProductFileEvent.
    """
    return PG_ENUM(
        ProductFileEvent,
        name=name,
        create_type=False,
        values_callable=lambda x: [e.value for e in x]
    )


__all__ = ["ProductFileEvent", "as_pg_enum"]

