# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/enums/rag_phase_enum.py

Fase 1 del pipeline RAG (preparación/indexación):
1) convert (conversión de binario a texto, NO incluye OCR)
2) ocr (paso explícito de OCR con Azure Cognitive Services para documentos escaneados)
3) chunk (segmentación semántica)
4) embed (generación de embeddings)
5) integrate (persistencia en la base vectorial con metadatos)
6) ready (documento indexado y listo para consulta)

Nota sobre OCR: Se ejecuta como fase independiente y explícita para documentos 
escaneados o imágenes, utilizando Azure Cognitive Services. Esto permite 
trazabilidad clara y métricas no ambiguas del pipeline.

Además, estados de job para ejecución y monitoreo (RagJobPhase).

Transiciones recomendadas: queued → convert → [ocr?] → chunk → embed → 
integrate → ready (completed/failed/cancelled para jobs).

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy import TypeDecorator


class RagPhase(StrEnum):
    """Fases del pipeline RAG de indexación."""
    convert   = "convert"    # conversión de binario a texto (NO incluye OCR)
    ocr       = "ocr"        # OCR explícito con Azure Cognitive Services
    chunk     = "chunk"      # segmentación semántica
    embed     = "embed"      # generación de embeddings
    integrate = "integrate"  # persistencia en vector store + metadatos
    ready     = "ready"      # documento indexado y listo para consulta


class RagJobPhase(StrEnum):
    """Estados de ejecución de un job de indexación RAG.
    
    Flujo típico: queued → running → completed/failed/cancelled
    El detalle granular de fases se gestiona con RagPhase.
    """
    queued     = "queued"     # job encolado, pendiente de ejecución
    running    = "running"    # job en ejecución (ver RagPhase para detalle)
    completed  = "completed"  # job finalizado exitosamente
    failed     = "failed"     # job falló durante ejecución
    cancelled  = "cancelled"  # job cancelado manualmente


# Valores canónicos para PostgreSQL
_RAG_PHASE_VALUES = ["convert", "ocr", "chunk", "embed", "integrate", "ready"]
_RAG_JOB_STATUS_VALUES = ["queued", "running", "completed", "failed", "cancelled"]


class RagPhaseType(TypeDecorator):
    """TypeDecorator para RagPhase enum → PostgreSQL rag_phase_enum."""
    impl = PG_ENUM(*_RAG_PHASE_VALUES, name="rag_phase_enum", create_type=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, RagPhase):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return RagPhase(value)


class RagJobPhaseType(TypeDecorator):
    """TypeDecorator para RagJobPhase enum → PostgreSQL rag_job_status_enum."""
    impl = PG_ENUM(*_RAG_JOB_STATUS_VALUES, name="rag_job_status_enum", create_type=False)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, RagJobPhase):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return RagJobPhase(value)


def as_pg_enum(name: str = "rag_phase_enum", schema: str | None = None) -> RagPhaseType:
    """Devuelve el TypeDecorator para RagPhase."""
    return RagPhaseType()


def rag_job_phase_as_pg_enum(name: str = "rag_job_status_enum", schema: str | None = None) -> RagJobPhaseType:
    """Devuelve el TypeDecorator para RagJobPhase."""
    return RagJobPhaseType()


__all__ = [
    "RagPhase",
    "RagPhaseType",
    "RagJobPhase",
    "RagJobPhaseType",
    "as_pg_enum",
    "rag_job_phase_as_pg_enum",
]
