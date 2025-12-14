# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/services/test_chunking_service.py

Tests para ChunkingService - FASE 4.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 4)
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from app.modules.rag.services.chunking_service import ChunkingService
from app.modules.rag.schemas.indexing_schemas import ChunkCreate


@pytest.mark.asyncio
async def test_create_chunk_success(adb):
    """Test: Crear chunk cuando no existe."""
    
    file_id = uuid4()
    chunk_id = uuid4()
    
    mock_chunk = SimpleNamespace(
        chunk_id=chunk_id,
        file_id=file_id,
        chunk_index=0,
        text_content="Sample text chunk",
        token_count=5,
        created_at="2025-11-28T10:00:00Z",
    )
    
    with patch('app.modules.rag.services.chunking_service.chunk_metadata_repository') as MockRepo:
        MockRepo.get_by_file_and_index = AsyncMock(return_value=None)
        MockRepo.insert_chunks = AsyncMock(return_value=[mock_chunk])
        
        service = ChunkingService(adb)
        data = ChunkCreate(
            file_id=file_id,
            chunk_index=0,
            text_content="Sample text chunk",
            token_count=5,
        )
        
        response = await service.create_chunk(data)
        
        # Assertions
        assert response.chunk_id == chunk_id
        assert response.file_id == file_id
        assert response.chunk_index == 0
        assert response.text_content == "Sample text chunk"
        assert response.token_count == 5
        
        MockRepo.get_by_file_and_index.assert_called_once()
        MockRepo.insert_chunks.assert_called_once()


@pytest.mark.asyncio
async def test_create_chunk_idempotent(adb):
    """Test: No crear chunk duplicado, devolver existente."""
    
    file_id = uuid4()
    chunk_id = uuid4()
    
    existing_chunk = SimpleNamespace(
        chunk_id=chunk_id,
        file_id=file_id,
        chunk_index=0,
        text_content="Existing chunk",
        token_count=5,
        created_at="2025-11-28T09:00:00Z",
    )
    
    with patch('app.modules.rag.services.chunking_service.chunk_metadata_repository') as MockRepo:
        MockRepo.get_by_file_and_index = AsyncMock(return_value=existing_chunk)
        
        service = ChunkingService(adb)
        data = ChunkCreate(
            file_id=file_id,
            chunk_index=0,
            text_content="New text",
            token_count=3,
        )
        
        response = await service.create_chunk(data)
        
        # Assertions: debe devolver el existente
        assert response.chunk_id == chunk_id
        assert response.text_content == "Existing chunk"  # not "New text"
        
        MockRepo.get_by_file_and_index.assert_called_once()
        MockRepo.insert_chunks.assert_not_called()


@pytest.mark.asyncio
async def test_list_file_chunks(adb):
    """Test: Listar chunks de un archivo."""
    
    file_id = uuid4()
    
    mock_chunks = [
        SimpleNamespace(
            chunk_id=uuid4(),
            file_id=file_id,
            chunk_index=0,
            text_content="First chunk",
            token_count=5,
            created_at="2025-11-28T10:00:00Z",
        ),
        SimpleNamespace(
            chunk_id=uuid4(),
            file_id=file_id,
            chunk_index=1,
            text_content="Second chunk",
            token_count=6,
            created_at="2025-11-28T10:01:00Z",
        ),
    ]
    
    with patch('app.modules.rag.services.chunking_service.chunk_metadata_repository') as MockRepo:
        MockRepo.list_by_file = AsyncMock(return_value=mock_chunks)
        
        service = ChunkingService(adb)
        response = await service.list_file_chunks(file_id)
        
        # Assertions
        assert len(response) == 2
        assert response[0].chunk_index == 0
        assert response[0].text_content == "First chunk"
        assert response[1].chunk_index == 1
        assert response[1].text_content == "Second chunk"
        
        MockRepo.list_by_file.assert_called_once_with(adb, file_id)


@pytest.mark.asyncio
async def test_get_chunk_by_id_success(adb):
    """Test: Obtener chunk por ID."""
    
    chunk_id = uuid4()
    file_id = uuid4()
    
    mock_chunk = SimpleNamespace(
        chunk_id=chunk_id,
        file_id=file_id,
        chunk_index=0,
        text_content="Target chunk",
        token_count=5,
        created_at="2025-11-28T10:00:00Z",
    )
    
    with patch('app.modules.rag.services.chunking_service.chunk_metadata_repository') as MockRepo:
        MockRepo.get_by_id = AsyncMock(return_value=mock_chunk)
        
        service = ChunkingService(adb)
        response = await service.get_chunk(chunk_id)
        
        # Assertions
        assert response.chunk_id == chunk_id
        assert response.file_id == file_id
        assert response.text_content == "Target chunk"
        
        MockRepo.get_by_id.assert_called_once_with(adb, chunk_id)


@pytest.mark.asyncio
async def test_get_chunk_not_found(adb):
    """Test: Error cuando chunk no existe."""
    
    chunk_id = uuid4()
    
    with patch('app.modules.rag.services.chunking_service.chunk_metadata_repository') as MockRepo:
        MockRepo.get_by_id = AsyncMock(return_value=None)
        
        service = ChunkingService(adb)
        
        with pytest.raises(Exception) as exc_info:
            await service.get_chunk(chunk_id)
        
        assert "no encontrado" in str(exc_info.value).lower() or "404" in str(exc_info.value)


# Fin del archivo backend/tests/modules/rag/services/test_chunking_service.py
