# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/__init__.py

Módulo RAG (Retrieval-Augmented Generation) - Fase 1 Indexación.

Exporta:
- Modelos ORM (RagJob, RagJobEvent, ChunkMetadata, DocumentEmbedding)
- ENUMs consolidados (RagPhase, RagJobPhase, OcrOptimization, FileCategory, InputProcessingStatus)
- Routers HTTP (get_rag_routers)

Patrón v2: alineado con módulos auth, payments, projects, files.

Autor: DoxAI
Fecha: 2025-11-28
"""

from .models import RagJob, RagJobEvent, ChunkMetadata, DocumentEmbedding
from .enums import (
    RagPhase,
    RagJobPhase,
    OcrOptimization,
    FileCategory,
    InputProcessingStatus,
)
from .routes import get_rag_routers, router

__all__ = [
    # Models
    "RagJob",
    "RagJobEvent",
    "ChunkMetadata",
    "DocumentEmbedding",
    # Enums
    "RagPhase",
    "RagJobPhase",
    "OcrOptimization",
    "FileCategory",
    "InputProcessingStatus",
    # Routes
    "get_rag_routers",
    "router",
]

# Fin del archivo backend/app/modules/rag/__init__.py
