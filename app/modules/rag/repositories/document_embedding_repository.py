# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/repositories/document_embedding_repository.py

Repositorio async para embeddings de documentos (pgvector).

Responsabilidades:
- CRUD básico sobre DocumentEmbedding
- Listados por archivo
- Búsqueda de similaridad semántica
- Verificación de idempotencia

Autor: DoxAI
Fecha: 2025-11-28
"""

from __future__ import annotations

from typing import Optional, Sequence, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.models.embedding_models import DocumentEmbedding


class DocumentEmbeddingRepository:
    """Repositorio para DocumentEmbedding con operaciones async."""
    
    async def insert_embeddings(
        self,
        session: AsyncSession,
        embeddings: List[DocumentEmbedding],
    ) -> Sequence[DocumentEmbedding]:
        """
        Inserta múltiples embeddings en batch.
        
        Args:
            session: Sesión async de SQLAlchemy
            embeddings: Lista de instancias DocumentEmbedding
            
        Returns:
            Secuencia de DocumentEmbedding creados
        """
        session.add_all(embeddings)
        await session.flush()
        
        # Refresh all embeddings to get generated IDs
        for emb in embeddings:
            await session.refresh(emb)
        
        return embeddings

    async def get_by_id(
        self,
        session: AsyncSession,
        embedding_id: UUID,
    ) -> Optional[DocumentEmbedding]:
        """
        Obtiene un embedding por su ID.
        
        Args:
            session: Sesión async de SQLAlchemy
            embedding_id: ID del embedding
            
        Returns:
            Instancia de DocumentEmbedding o None si no existe
        """
        stmt = select(DocumentEmbedding).where(
            DocumentEmbedding.embedding_id == embedding_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_file(
        self,
        session: AsyncSession,
        file_id: UUID,
        *,
        only_active: bool = True,
    ) -> Sequence[DocumentEmbedding]:
        """
        Lista todos los embeddings de un archivo.
        
        Args:
            session: Sesión async de SQLAlchemy
            file_id: ID del archivo
            only_active: Si True, solo devuelve embeddings activos
            
        Returns:
            Secuencia de DocumentEmbedding ordenados por índice de chunk
        """
        conditions = [DocumentEmbedding.file_id == file_id]
        if only_active:
            conditions.append(DocumentEmbedding.is_active == True)
        
        stmt = (
            select(DocumentEmbedding)
            .where(and_(*conditions))
            .order_by(DocumentEmbedding.chunk_index.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count_by_file(
        self,
        session: AsyncSession,
        file_id: UUID,
        *,
        only_active: bool = True,
    ) -> int:
        """
        Cuenta los embeddings de un archivo.
        
        Args:
            session: Sesión async de SQLAlchemy
            file_id: ID del archivo
            only_active: Si True, solo cuenta embeddings activos
            
        Returns:
            Número de embeddings
        """
        conditions = [DocumentEmbedding.file_id == file_id]
        if only_active:
            conditions.append(DocumentEmbedding.is_active == True)
        
        stmt = (
            select(func.count())
            .select_from(DocumentEmbedding)
            .where(and_(*conditions))
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def exists_for_file_and_chunk(
        self,
        session: AsyncSession,
        file_id: UUID,
        chunk_index: int,
        embedding_model: str,
    ) -> bool:
        """
        Verifica si ya existe un embedding para un archivo, chunk y modelo específicos.
        Útil para idempotencia.
        
        Args:
            session: Sesión async de SQLAlchemy
            file_id: ID del archivo
            chunk_index: Índice del chunk
            embedding_model: Nombre del modelo de embedding
            
        Returns:
            True si existe, False en caso contrario
        """
        stmt = (
            select(func.count())
            .select_from(DocumentEmbedding)
            .where(
                DocumentEmbedding.file_id == file_id,
                DocumentEmbedding.chunk_index == chunk_index,
                DocumentEmbedding.embedding_model == embedding_model,
                DocumentEmbedding.is_active == True,
            )
        )
        result = await session.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    async def mark_inactive(
        self,
        session: AsyncSession,
        file_id: UUID,
    ) -> int:
        """
        Marca todos los embeddings de un archivo como inactivos (borrado lógico).
        
        Args:
            session: Sesión async de SQLAlchemy
            file_id: ID del archivo
            
        Returns:
            Número de embeddings marcados como inactivos
        """
        stmt = (
            select(DocumentEmbedding)
            .where(
                DocumentEmbedding.file_id == file_id,
                DocumentEmbedding.is_active == True,
            )
        )
        result = await session.execute(stmt)
        embeddings = result.scalars().all()
        
        now = datetime.now(timezone.utc)
        count = 0
        for emb in embeddings:
            emb.is_active = False
            emb.deleted_at = now
            count += 1
        
        if count > 0:
            await session.flush()
        
        return count


# Instancia global para uso en facades
document_embedding_repository = DocumentEmbeddingRepository()


__all__ = [
    "DocumentEmbeddingRepository",
    "document_embedding_repository",
]

# Fin del archivo backend/app/modules/rag/repositories/document_embedding_repository.py
