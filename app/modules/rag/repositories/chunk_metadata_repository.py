# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/repositories/chunk_metadata_repository.py

Repositorio async para metadatos de chunks de documentos.

Responsabilidades:
- CRUD básico sobre ChunkMetadata
- Listados por archivo
- Conteo de chunks por archivo
- Consultas por rango de páginas

Autor: DoxAI
Fecha: 2025-11-28
Actualizado: 2025-11-28 - FASE B: Convertido a clase y alineación con SQL
"""

from __future__ import annotations

from typing import Optional, Sequence, List
from uuid import UUID

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.models.chunk_models import ChunkMetadata


class ChunkMetadataRepository:
    """
    Repositorio para gestión de metadatos de chunks.
    
    Responsabilidades:
    - CRUD básico sobre ChunkMetadata
    - Listados y conteos por archivo
    - Eliminación de chunks para idempotencia
    """
    
    async def insert_chunks(
        self,
        session: AsyncSession,
        chunks: List[ChunkMetadata],
    ) -> Sequence[ChunkMetadata]:
        """
        Inserta múltiples chunks en batch.
        
        Args:
            session: Sesión async de SQLAlchemy
            chunks: Lista de instancias ChunkMetadata
            
        Returns:
            Secuencia de ChunkMetadata creados
            
        Nota:
            FASE 2 - Issue #21: Optimizado para evitar refresh en loop.
            Como chunk_id se genera con default=uuid4 en el ORM,
            los IDs ya están disponibles antes del flush.
            Solo hacemos flush para persistir en DB.
        """
        session.add_all(chunks)
        await session.flush()
        
        # Los chunk_id ya están disponibles (generados por uuid4 en __init__)
        # No necesitamos refresh individual, solo el flush para persistir
        
        return chunks

    async def get_by_id(
        self,
        session: AsyncSession,
        chunk_id: UUID,
    ) -> Optional[ChunkMetadata]:
        """
        Obtiene un chunk por su ID.
        
        Args:
            session: Sesión async de SQLAlchemy
            chunk_id: ID del chunk
            
        Returns:
            Instancia de ChunkMetadata o None si no existe
        """
        stmt = select(ChunkMetadata).where(ChunkMetadata.chunk_id == chunk_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_file(
        self,
        session: AsyncSession,
        file_id: UUID,
    ) -> Sequence[ChunkMetadata]:
        """
        Lista todos los chunks de un archivo.
        
        Args:
            session: Sesión async de SQLAlchemy
            file_id: ID del archivo
            
        Returns:
            Secuencia de ChunkMetadata ordenados por índice
        """
        stmt = (
            select(ChunkMetadata)
            .where(ChunkMetadata.file_id == file_id)
            .order_by(ChunkMetadata.chunk_index.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count_by_file(
        self,
        session: AsyncSession,
        file_id: UUID,
    ) -> int:
        """
        Cuenta los chunks de un archivo.
        
        Args:
            session: Sesión async de SQLAlchemy
            file_id: ID del archivo
            
        Returns:
            Número de chunks
        """
        stmt = (
            select(func.count())
            .select_from(ChunkMetadata)
            .where(ChunkMetadata.file_id == file_id)
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def get_by_file_and_index(
        self,
        session: AsyncSession,
        file_id: UUID,
        chunk_index: int,
    ) -> Optional[ChunkMetadata]:
        """
        Obtiene un chunk específico por archivo e índice.
        
        Args:
            session: Sesión async de SQLAlchemy
            file_id: ID del archivo
            chunk_index: Índice del chunk
            
        Returns:
            Instancia de ChunkMetadata o None si no existe
        """
        stmt = select(ChunkMetadata).where(
            ChunkMetadata.file_id == file_id,
            ChunkMetadata.chunk_index == chunk_index,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_file(
        self,
        session: AsyncSession,
        file_id: UUID,
    ) -> int:
        """
        Elimina todos los chunks de un archivo (para idempotencia).
        
        Args:
            session: Sesión async de SQLAlchemy
            file_id: ID del archivo
            
        Returns:
            Número de chunks eliminados
        """
        stmt = delete(ChunkMetadata).where(ChunkMetadata.file_id == file_id)
        result = await session.execute(stmt)
        return result.rowcount


# Instancia global para compatibilidad
chunk_metadata_repository = ChunkMetadataRepository()


__all__ = [
    "ChunkMetadataRepository",
    "chunk_metadata_repository",
]

# Fin del archivo backend/app/modules/rag/repositories/chunk_metadata_repository.py
