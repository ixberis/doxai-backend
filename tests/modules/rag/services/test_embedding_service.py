# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/services/test_embedding_service.py

Tests para EmbeddingService - FASE 4.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 4)
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from app.modules.rag.services.embedding_service import EmbeddingService
from app.modules.rag.schemas.indexing_schemas import EmbeddingCreate
from app.modules.rag.enums import RagPhase


@pytest.mark.asyncio
async def test_create_embedding_success(adb):
    """Test: Crear embedding cuando no existe."""
    
    file_id = uuid4()
    chunk_id = uuid4()
    embedding_id = uuid4()
    
    mock_chunk = SimpleNamespace(
        chunk_id=chunk_id,
        file_id=file_id,
        chunk_index=0,
    )
    
    mock_embedding = SimpleNamespace(
        embedding_id=embedding_id,
        file_id=file_id,
        chunk_index=0,
        embedding_model="text-embedding-3-large",
        created_at="2025-11-28T10:00:00Z",
    )
    
    with patch('app.modules.rag.services.embedding_service.chunk_metadata_repository') as MockChunkRepo, \
         patch('app.modules.rag.services.embedding_service.document_embedding_repository') as MockRepo:
        MockChunkRepo.get_by_file_and_index = AsyncMock(return_value=mock_chunk)
        MockRepo.exists_for_file_and_chunk = AsyncMock(return_value=False)
        MockRepo.insert_embeddings = AsyncMock(return_value=[mock_embedding])
        
        service = EmbeddingService(adb)
        data = EmbeddingCreate(
            file_id=file_id,
            chunk_index=0,
            text_chunk="Sample text",
            vector=[0.1] * 1536,
            embedding_model="text-embedding-3-large",
            rag_phase=RagPhase.embed,
        )
        
        response = await service.create_embedding(data)
        
        # Assertions
        assert response.embedding_id == embedding_id
        assert response.file_id == file_id
        assert response.chunk_index == 0
        assert response.embedding_model == "text-embedding-3-large"
        
        MockChunkRepo.get_by_file_and_index.assert_called_once()
        MockRepo.exists_for_file_and_chunk.assert_called_once()
        MockRepo.insert_embeddings.assert_called_once()


@pytest.mark.asyncio
async def test_create_embedding_idempotent(adb):
    """Test: No crear embedding duplicado, devolver existente."""
    
    file_id = uuid4()
    embedding_id = uuid4()
    
    existing_embedding = SimpleNamespace(
        embedding_id=embedding_id,
        file_id=file_id,
        chunk_index=0,
        embedding_model="text-embedding-3-large",
        created_at="2025-11-28T09:00:00Z",
    )
    
    with patch('app.modules.rag.services.embedding_service.document_embedding_repository') as MockRepo:
        # exists_for_file_and_chunk ahora devuelve un booleano
        MockRepo.exists_for_file_and_chunk = AsyncMock(return_value=True)
        # list_by_file devuelve la lista con el embedding existente
        MockRepo.list_by_file = AsyncMock(return_value=[existing_embedding])
        
        service = EmbeddingService(adb)
        data = EmbeddingCreate(
            file_id=file_id,
            chunk_index=0,
            text_chunk="Sample text",
            vector=[0.1] * 1536,
            embedding_model="text-embedding-3-large",
            rag_phase=RagPhase.embed,
        )
        
        response = await service.create_embedding(data)
        
        # Assertions: debe devolver el existente
        assert response.embedding_id == embedding_id
        
        MockRepo.exists_for_file_and_chunk.assert_called_once()
        MockRepo.list_by_file.assert_called_once()


@pytest.mark.asyncio
async def test_list_file_embeddings(adb):
    """Test: Listar embeddings de un archivo."""
    
    file_id = uuid4()
    
    mock_embeddings = [
        SimpleNamespace(
            embedding_id=uuid4(),
            file_id=file_id,
            chunk_index=0,
            embedding_model="text-embedding-3-large",
            created_at="2025-11-28T10:00:00Z",
        ),
        SimpleNamespace(
            embedding_id=uuid4(),
            file_id=file_id,
            chunk_index=1,
            embedding_model="text-embedding-3-large",
            created_at="2025-11-28T10:01:00Z",
        ),
    ]
    
    with patch('app.modules.rag.services.embedding_service.document_embedding_repository') as MockRepo:
        MockRepo.list_by_file = AsyncMock(return_value=mock_embeddings)
        
        service = EmbeddingService(adb)
        response = await service.list_file_embeddings(file_id)
        
        # Assertions
        assert len(response) == 2
        assert response[0].chunk_index == 0
        assert response[1].chunk_index == 1
        
        MockRepo.list_by_file.assert_called_once_with(adb, file_id, only_active=True)


@pytest.mark.asyncio
async def test_delete_file_embeddings(adb):
    """Test: Marcar embeddings como inactivos."""
    
    file_id = uuid4()
    
    with patch('app.modules.rag.services.embedding_service.document_embedding_repository') as MockRepo:
        MockRepo.mark_inactive = AsyncMock(return_value=5)
        
        service = EmbeddingService(adb)
        count = await service.delete_file_embeddings(file_id)
        
        # Assertions
        assert count == 5
        
        MockRepo.mark_inactive.assert_called_once_with(adb, file_id)


# Fin del archivo backend/tests/modules/rag/services/test_embedding_service.py
