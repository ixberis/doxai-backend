# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/services/chunking_service.py

Servicio para chunking semántico de documentos.

Este servicio divide documentos en chunks para procesamiento
y generación de embeddings.

REFACTORIZADO v2: Usa chunk_metadata_repository en lugar de queries directas.

Autor: DoxAI
Fecha: 2025-10-18 (actualizado 2025-11-28)
"""

import logging
from typing import List
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.models.chunk_models import ChunkMetadata
from app.modules.rag.schemas.indexing_schemas import (
    ChunkCreate,
    ChunkResponse,
)
from app.modules.rag.repositories import chunk_metadata_repository

logger = logging.getLogger(__name__)


class ChunkingService:
    """
    Servicio para gestión de chunks de documentos.
    
    Responsabilidades:
    - Crear chunks de texto
    - Consultar chunks por archivo
    - Gestionar metadatos de chunks
    
    v2: Usa chunk_metadata_repository.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_chunk(
        self, 
        data: ChunkCreate
    ) -> ChunkResponse:
        """
        Crea un nuevo chunk con sus metadatos.
        
        Args:
            data: Datos del chunk
            
        Returns:
            ChunkResponse con información del chunk creado
        """
        # Verificar si ya existe un chunk con el mismo índice
        existing = await chunk_metadata_repository.get_by_file_and_index(
            self.db,
            file_id=data.file_id,
            chunk_index=data.chunk_index,
        )
        
        if existing:
            logger.warning(
                f"Chunk already exists for file {data.file_id}, "
                f"index {data.chunk_index}. Returning existing."
            )
            return ChunkResponse(
                chunk_id=existing.chunk_id,
                file_id=existing.file_id,
                chunk_index=existing.chunk_index,
                text_content=getattr(existing, "chunk_text", getattr(existing, "text_content", None)),
                token_count=existing.token_count,
                created_at=existing.created_at,
            )
        
        # Crear nuevo chunk
        chunk = ChunkMetadata(
            file_id=data.file_id,
            chunk_index=data.chunk_index,
            chunk_text=data.text_content,
            token_count=data.token_count,
            source_page_start=data.source_page_start,
            source_page_end=data.source_page_end,
            metadata_json=data.metadata,
        )
        
        try:
            chunks = await chunk_metadata_repository.insert_chunks(
                self.db,
                [chunk],
            )
            created_chunk = chunks[0]
            
            logger.info(
                f"Created chunk for file {data.file_id}, "
                f"index {data.chunk_index}"
            )
            
            return ChunkResponse(
                chunk_id=created_chunk.chunk_id,
                file_id=created_chunk.file_id,
                chunk_index=created_chunk.chunk_index,
                text_content=getattr(created_chunk, "chunk_text", getattr(created_chunk, "text_content", None)),
                token_count=created_chunk.token_count,
                created_at=created_chunk.created_at,
            )
        except Exception as e:
            logger.error(f"Error creating chunk: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error al crear chunk: {str(e)}"
            )
    
    async def list_file_chunks(
        self, 
        file_id: UUID
    ) -> List[ChunkResponse]:
        """
        Lista chunks de un archivo.
        
        Args:
            file_id: ID del archivo
            
        Returns:
            Lista de ChunkResponse
        """
        chunks = await chunk_metadata_repository.list_by_file(
            self.db,
            file_id,
        )
        
        logger.info(f"Found {len(chunks)} chunks for file {file_id}")
        
        return [
            ChunkResponse(
                chunk_id=chunk.chunk_id,
                file_id=chunk.file_id,
                chunk_index=chunk.chunk_index,
                text_content=getattr(chunk, "chunk_text", getattr(chunk, "text_content", None)),
                token_count=chunk.token_count,
                created_at=chunk.created_at,
            )
            for chunk in chunks
        ]
    
    async def get_chunk(
        self, 
        chunk_id: UUID
    ) -> ChunkResponse:
        """
        Obtiene un chunk por su ID.
        
        Args:
            chunk_id: ID del chunk
            
        Returns:
            ChunkResponse con información del chunk
            
        Raises:
            HTTPException: Si el chunk no existe
        """
        chunk = await chunk_metadata_repository.get_by_id(
            self.db,
            chunk_id,
        )
        
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk no encontrado")
        
        return ChunkResponse(
            chunk_id=chunk.chunk_id,
            file_id=chunk.file_id,
            chunk_index=chunk.chunk_index,
            text_content=getattr(chunk, "chunk_text", getattr(chunk, "text_content", None)),
            token_count=chunk.token_count,
            created_at=chunk.created_at,
        )
