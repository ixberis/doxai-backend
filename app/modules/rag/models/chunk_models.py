# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/models/chunk_models.py

Modelo ORM para metadatos de chunks.

Este modelo almacena información sobre chunks de texto generados
durante el proceso de chunking semántico.

Autor: DoxAI
Fecha: 2025-10-18
Actualizado: 2025-11-28 - Alineación con SQL (chunk_text, source_page_*, metadata_json)
"""

from uuid import uuid4
from sqlalchemy import Column, String, Text, Integer, DateTime, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.shared.database.database import Base


class ChunkMetadata(Base):
    """
    Metadatos de chunks generados durante el procesamiento.
    
    Atributos:
        chunk_id: Identificador único del chunk
        file_id: ID del archivo fuente
        chunk_index: Índice del chunk dentro del documento
        chunk_text: Contenido de texto del chunk (alineado con SQL)
        token_count: Número de tokens
        source_page_start: Página inicial del chunk (alineado con SQL)
        source_page_end: Página final del chunk (alineado con SQL)
        metadata_json: Metadatos adicionales en formato JSONB (alineado con SQL)
        created_at: Timestamp de creación
    """
    __tablename__ = "chunk_metadata"
    
    __table_args__ = (
        UniqueConstraint("file_id", "chunk_index", name="uq_chunk_file_index"),
        CheckConstraint("token_count >= 0", name="check_chunk_token_count_positive"),
        CheckConstraint("source_page_start >= 0", name="check_chunk_page_start_positive"),
        CheckConstraint("source_page_end >= 0", name="check_chunk_page_end_positive"),
    )

    chunk_id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4,
        comment="Identificador único del chunk"
    )

    file_id = Column(
        UUID(as_uuid=True), 
        nullable=False,
        comment="ID del archivo fuente"
    )

    chunk_index = Column(
        Integer, 
        nullable=False,
        comment="Índice del chunk en el documento"
    )

    chunk_text = Column(
        Text, 
        nullable=False,
        comment="Contenido de texto del chunk"
    )

    token_count = Column(
        Integer, 
        CheckConstraint("token_count >= 0", name="check_chunk_token_count_positive"), 
        nullable=False,
        default=0,
        comment="Número de tokens del chunk"
    )

    source_page_start = Column(
        Integer, 
        CheckConstraint("source_page_start >= 0", name="check_chunk_page_start_positive"), 
        nullable=True,
        comment="Página inicial del chunk"
    )

    source_page_end = Column(
        Integer, 
        CheckConstraint("source_page_end >= 0", name="check_chunk_page_end_positive"), 
        nullable=True,
        comment="Página final del chunk"
    )

    metadata_json = Column(
        JSONB, 
        nullable=True,
        server_default=func.text("'{}'::jsonb"),
        comment="Metadatos adicionales en formato JSONB"
    )

    created_at = Column(
        DateTime, 
        nullable=False, 
        server_default=func.now(),
        comment="Timestamp de creación"
    )

    updated_at = Column(
        DateTime, 
        nullable=False, 
        server_default=func.now(),
        onupdate=func.now(),
        comment="Timestamp de última actualización"
    )

    def __repr__(self):
        return f"<ChunkMetadata(id={self.chunk_id}, file={self.file_id}, index={self.chunk_index})>"

# Fin del archivo
