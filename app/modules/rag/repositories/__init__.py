# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/repositories/__init__.py

Repositorios para el módulo RAG v2.

Autor: DoxAI
Fecha: 2025-11-28
"""

from app.modules.rag.repositories.rag_job_repository import (
    RagJobRepository, 
    rag_job_repository
)
from app.modules.rag.repositories.rag_job_event_repository import (
    RagJobEventRepository, 
    rag_job_event_repository
)
from app.modules.rag.repositories.chunk_metadata_repository import (
    ChunkMetadataRepository,
    chunk_metadata_repository
)
from app.modules.rag.repositories.document_embedding_repository import (
    DocumentEmbeddingRepository,
    document_embedding_repository
)

__all__ = [
    "RagJobRepository",
    "rag_job_repository",
    "RagJobEventRepository",
    "rag_job_event_repository",
    "ChunkMetadataRepository",
    "chunk_metadata_repository",
    "DocumentEmbeddingRepository",
    "document_embedding_repository",
]

# Fin del archivo backend/app/modules/rag/repositories/__init__.py
