# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/facades/__init__.py

API pública de facades del pipeline RAG v2.
Orquesta convert → ocr → chunk → embed → integrate → ready.

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 2)
"""

from .convert_facade import convert_to_text, ConvertedText
from .ocr_facade import run_ocr, OcrText
from .chunk_facade import chunk_text, ChunkParams, ChunkingResult
from .embed_facade import generate_embeddings, ChunkSelector, EmbeddingResult
from .integrate_facade import integrate_vector_index, IntegrationResult
from .orchestrator_facade import run_indexing_job, OrchestrationSummary

__all__ = [
    # Convert
    "convert_to_text",
    "ConvertedText",
    # OCR
    "run_ocr",
    "OcrText",
    # Chunking
    "chunk_text",
    "ChunkParams",
    "ChunkingResult",
    # Embeddings
    "generate_embeddings",
    "ChunkSelector",
    "EmbeddingResult",
    # Integration
    "integrate_vector_index",
    "IntegrationResult",
    # Orchestrator
    "run_indexing_job",
    "OrchestrationSummary",
]
