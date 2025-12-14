# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/models/embedding_models.py

Modelo ORM para embeddings de documentos.

Este modelo almacena vectores generados a partir de chunks de texto
para permitir búsqueda semántica y recuperación de contexto.

Autor: DoxAI
Fecha: 2025-10-18
"""

# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/models/embedding_models.py

Modelo ORM para embeddings de documentos (pgvector).
"""

from uuid import uuid4
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer,
    Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.shared.database.database import Base
# ✅ usa los enums consolidados desde rag.enums (que importa de files):
from app.modules.rag.enums import file_category_as_pg_enum, RagPhaseType


class DocumentEmbedding(Base):
    __tablename__ = "document_embeddings"

    embedding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    file_id = Column(UUID(as_uuid=True), nullable=False)
    
    chunk_id = Column(UUID(as_uuid=True), nullable=False)

    file_category = Column(
        file_category_as_pg_enum(),  # TypeDecorator para file_category_enum
        nullable=False
    )

    # ✅ usar TypeDecorator para rag_phase_enum
    rag_phase = Column(
        RagPhaseType(),
        nullable=True
    )

    chunk_index = Column(Integer, nullable=False)

    # Dimensión definida de facto: 1536
    embedding_vector = Column(Vector(1536), nullable=False)

    embedding_model = Column(String(100), nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)

    deleted_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # ✅ Idempotencia y aceleradores que tus tests esperan
    __table_args__ = (
        UniqueConstraint(
            "file_id", "chunk_index", "embedding_model",
            name="uq_document_embeddings_key"
        ),
        Index(
            "idx_embedding_file_active",
            "file_id", "is_active"
        ),
    )

    def __repr__(self):
        return f"<DocumentEmbedding(id={self.embedding_id}, file={self.file_id}, chunk={self.chunk_index})>"
# Fin del archivo
