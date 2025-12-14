
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/enums/input_processing_status_enum.py

Estado de procesamiento de archivos de entrada (insumos) en Fase 1.

Valores **canónicos** (minúsculas):
- uploaded   : el archivo fue recibido
- queued     : encolado y listo para procesarse
- processing : en proceso (sub-fases converting/chunking/embedding)
- parsed     : extracción/parseo completo (equivalente a 'completed')
- vectorized : embeddings generados (indexado listo)
- failed     : error permanente

Aliases de compatibilidad:
- completed  -> parsed
- converting, chunking, embedding -> processing
- extracting -> processing
- extracted  -> parsed
- indexing   -> vectorized
- canceled   -> failed
- pending    -> queued

Notas:
- En los modelos, se recomienda:
  * InputFile.status → default = 'uploaded'
  * InputFileMetadata.status → default = 'queued'
  Esto mantiene consistencia del pipeline "uploaded → queued → processing → parsed → vectorized".

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""

from __future__ import annotations

from typing import Any
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy import TypeDecorator

from .compat_base import _StrEnum, EnumMixin


class InputProcessingStatus(EnumMixin, _StrEnum):
    # --- valores canónicos (usados en tests y modelos) ---
    uploaded   = "uploaded"
    queued     = "queued"
    processing = "processing"
    parsed     = "parsed"
    vectorized = "vectorized"
    failed     = "failed"

    # --- aliases de compatibilidad ---
    completed  = parsed
    converting = processing
    chunking   = processing
    embedding  = processing
    extracting = processing
    extracted  = parsed
    indexing   = vectorized
    canceled   = failed
    pending    = queued
    
    # --- aliases en mayúsculas para tests legacy ---
    UPLOADED   = uploaded
    QUEUED     = queued
    PROCESSING = processing
    PARSED     = parsed
    VECTORIZED = vectorized
    FAILED     = failed
    COMPLETED  = parsed
    PENDING    = queued

    @classmethod
    def _missing_(cls, value: Any):
        """
        Normaliza entradas string legacy/sinónimos al valor canónico.
        """
        if isinstance(value, str):
            v = value.strip().lower()
            mapping = {
                # canónicos
                "uploaded": "uploaded",
                "queued": "queued",
                "processing": "processing",
                "parsed": "parsed",
                "vectorized": "vectorized",
                "failed": "failed",
                # compat
                "completed": "parsed",
                "converting": "processing",
                "chunking": "processing",
                "embedding": "processing",
                "extracting": "processing",
                "extracted": "parsed",
                "indexing": "vectorized",
                "canceled": "failed",
                "pending": "queued",
            }
            target = mapping.get(v)
            if target:
                return getattr(cls, target)
        raise ValueError(f"{value!r} is not a valid {cls.__name__}")


PG_TYPE_NAME = "input_processing_status_enum"

# Valores canónicos para PostgreSQL
_INPUT_PROCESSING_STATUS_VALUES = [
    "uploaded",
    "queued",
    "processing",
    "parsed",
    "vectorized",
    "failed",
]


class InputProcessingStatusType(TypeDecorator):
    """
    TypeDecorator para mapear InputProcessingStatus a input_processing_status_enum de PostgreSQL.
    """
    impl = PG_ENUM(*_INPUT_PROCESSING_STATUS_VALUES, name=PG_TYPE_NAME, create_type=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, InputProcessingStatus):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return InputProcessingStatus(value)


def input_processing_status_as_pg_enum(
    name: str = PG_TYPE_NAME,
) -> InputProcessingStatusType:
    """
    Factory de tipo ENUM para SQLAlchemy/Postgres.
    Devuelve TypeDecorator que maneja correctamente la coerción de tipos.
    """
    return InputProcessingStatusType()


__all__ = ["InputProcessingStatus", "InputProcessingStatusType", "input_processing_status_as_pg_enum"]

# Fin del archivo backend\app\modules\files\enums\input_processing_status_enum.py
