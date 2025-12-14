# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/services/embedding_service.py

Servicio para generación y gestión de embeddings.

Este servicio maneja la creación de vectores de embedding
a partir de chunks de texto.

REFACTORIZADO v2: Usa document_embedding_repository en lugar de queries directas.

Autor: DoxAI
Fecha: 2025-10-18 (actualizado 2025-11-28)
"""

import logging
from typing import List
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.models.embedding_models import DocumentEmbedding
from app.modules.rag.schemas.indexing_schemas import (
    EmbeddingCreate,
    EmbeddingResponse,
)
from app.modules.rag.enums import FileCategory
from app.modules.rag.repositories import (
    document_embedding_repository,
    chunk_metadata_repository,
)

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Servicio para gestión de embeddings.
    
    Responsabilidades:
    - Crear embeddings vectoriales
    - Consultar embeddings por archivo
    - Eliminar embeddings obsoletos
    
    v2: Usa document_embedding_repository.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_embedding(
        self, 
        data: EmbeddingCreate,
        file_category: FileCategory = FileCategory.input
    ) -> EmbeddingResponse:
        """
        Crea un nuevo embedding.
        
        Args:
            data: Datos del embedding
            file_category: Categoría del archivo fuente
            
        Returns:
            EmbeddingResponse con información del embedding creado
        """
        # Verificar idempotencia
        exists = await document_embedding_repository.exists_for_file_and_chunk(
            self.db,
            file_id=data.file_id,
            chunk_index=data.chunk_index,
            embedding_model=data.embedding_model,
        )
        
        if exists:
            logger.warning(
                f"Embedding already exists for file {data.file_id}, "
                f"chunk {data.chunk_index}, model {data.embedding_model}"
            )
            # Obtener el embedding existente
            embeddings = await document_embedding_repository.list_by_file(
                self.db,
                file_id=data.file_id,
                only_active=True,
            )
            for emb in embeddings:
                if (emb.chunk_index == data.chunk_index and 
                    emb.embedding_model == data.embedding_model):
                    return EmbeddingResponse(
                        embedding_id=emb.embedding_id,
                        file_id=emb.file_id,
                        chunk_index=emb.chunk_index,
                        embedding_model=emb.embedding_model,
                        created_at=emb.created_at,
                    )
        
        # Obtener chunk_id desde chunk_metadata
        chunk = await chunk_metadata_repository.get_by_file_and_index(
            self.db,
            file_id=data.file_id,
            chunk_index=data.chunk_index,
        )
        
        if not chunk:
            raise HTTPException(
                status_code=404,
                detail=f"Chunk no encontrado para file_id={data.file_id}, chunk_index={data.chunk_index}"
            )
        
        # Crear nuevo embedding
        embedding = DocumentEmbedding(
            file_id=data.file_id,
            chunk_id=chunk.chunk_id,
            file_category=file_category,
            rag_phase=data.rag_phase,
            chunk_index=data.chunk_index,
            embedding_vector=data.vector,
            embedding_model=data.embedding_model,
            is_active=True,
        )
        
        try:
            embeddings = await document_embedding_repository.insert_embeddings(
                self.db,
                [embedding],
            )
            created_emb = embeddings[0]
            
            logger.info(
                f"Created embedding for file {data.file_id}, "
                f"chunk {data.chunk_index}"
            )
            
            return EmbeddingResponse(
                embedding_id=created_emb.embedding_id,
                file_id=created_emb.file_id,
                chunk_index=created_emb.chunk_index,
                embedding_model=created_emb.embedding_model,
                created_at=created_emb.created_at,
            )
        except Exception as e:
            logger.error(f"Error creating embedding: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error al crear embedding: {str(e)}"
            )
    
    async def list_file_embeddings(
        self, 
        file_id: UUID
    ) -> List[EmbeddingResponse]:
        """
        Lista embeddings de un archivo.
        
        Args:
            file_id: ID del archivo
            
        Returns:
            Lista de EmbeddingResponse
        """
        embeddings = await document_embedding_repository.list_by_file(
            self.db,
            file_id,
            only_active=True,
        )
        
        logger.info(f"Found {len(embeddings)} embeddings for file {file_id}")
        
        return [
            EmbeddingResponse(
                embedding_id=emb.embedding_id,
                file_id=emb.file_id,
                chunk_index=emb.chunk_index,
                embedding_model=emb.embedding_model,
                created_at=emb.created_at,
            )
            for emb in embeddings
        ]
    
    async def delete_file_embeddings(
        self, 
        file_id: UUID
    ) -> int:
        """
        Elimina embeddings de un archivo (marcado lógico).
        
        Args:
            file_id: ID del archivo
            
        Returns:
            Número de embeddings eliminados
        """
        try:
            result = await document_embedding_repository.mark_inactive(
                self.db,
                file_id,
            )
            
            logger.info(f"Deleted {result} embeddings for file {file_id}")
            
            return result
        except Exception as e:
            logger.error(f"Error deleting embeddings: {str(e)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error al eliminar embeddings: {str(e)}"
            )
