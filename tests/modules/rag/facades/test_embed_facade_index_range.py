# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_embed_facade_index_range.py

Tests para ChunkSelector.index_range en embed_facade.

FASE 3 - Issue #35: Test de index_range selector

Autor: DoxAI
Fecha: 2025-11-28
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.modules.rag.facades.embed_facade import (
    generate_embeddings,
    ChunkSelector,
    EmbeddingResult,
)
from app.modules.rag.models import ChunkMetadata


@pytest.fixture
def sample_chunks_for_range():
    """Chunks de ejemplo para test de index_range."""
    file_id = uuid4()
    chunks = []
    for i in range(10):
        chunk = ChunkMetadata(
            file_id=file_id,
            chunk_index=i,
            chunk_text=f"Chunk {i} content with some text for embedding",
            token_count=10,
            source_page_start=i,
            source_page_end=i,
        )
        chunks.append(chunk)
    return chunks


@pytest.mark.asyncio
async def test_generate_embeddings_with_index_range_full(sample_chunks_for_range):
    """Test generación de embeddings con index_range completo (0-9)."""
    job_id = uuid4()
    file_id = sample_chunks_for_range[0].file_id
    
    # Mock repositories
    from app.modules.rag.repositories import (
        RagJobRepository,
        RagJobEventRepository,
        ChunkMetadataRepository,
        DocumentEmbeddingRepository,
    )
    
    job_repo = Mock(spec=RagJobRepository)
    event_repo = Mock(spec=RagJobEventRepository)
    event_repo.log_event = AsyncMock()
    
    chunk_repo = Mock(spec=ChunkMetadataRepository)
    # list_by_file retorna todos los chunks
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks_for_range)
    
    embedding_repo = Mock(spec=DocumentEmbeddingRepository)
    embedding_repo.exists_for_file_and_chunk = AsyncMock(return_value=False)
    embedding_repo.insert_embeddings = AsyncMock(
        side_effect=lambda db, embs: embs  # Retorna los embeddings tal cual
    )
    
    # Mock OpenAI embeddings function
    with patch(
        'app.modules.rag.facades.embed_facade.openai_generate_embeddings',
        new=AsyncMock(return_value=[[0.1] * 1536 for _ in range(10)])
    ):
        selector = ChunkSelector(index_range=(0, 9))
        
        result = await generate_embeddings(
            db=AsyncMock(),
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=selector,
            openai_api_key="test-key",
            job_repo=job_repo,
            event_repo=event_repo,
            chunk_repo=chunk_repo,
            embedding_repo=embedding_repo,
        )
    
    assert isinstance(result, EmbeddingResult)
    assert result.total_chunks == 10
    assert result.embedded == 10
    assert result.skipped == 0


@pytest.mark.asyncio
async def test_generate_embeddings_with_index_range_partial(sample_chunks_for_range):
    """Test generación de embeddings con index_range parcial (0-4)."""
    job_id = uuid4()
    file_id = sample_chunks_for_range[0].file_id
    
    # Mock repositories
    from app.modules.rag.repositories import (
        RagJobRepository,
        RagJobEventRepository,
        ChunkMetadataRepository,
        DocumentEmbeddingRepository,
    )
    
    job_repo = Mock(spec=RagJobRepository)
    event_repo = Mock(spec=RagJobEventRepository)
    event_repo.log_event = AsyncMock()
    
    chunk_repo = Mock(spec=ChunkMetadataRepository)
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks_for_range)
    
    embedding_repo = Mock(spec=DocumentEmbeddingRepository)
    embedding_repo.exists_for_file_and_chunk = AsyncMock(return_value=False)
    embedding_repo.insert_embeddings = AsyncMock(
        side_effect=lambda db, embs: embs
    )
    
    # Mock OpenAI embeddings function
    with patch(
        'app.modules.rag.facades.embed_facade.openai_generate_embeddings',
        new=AsyncMock(return_value=[[0.1] * 1536 for _ in range(5)])
    ):
        selector = ChunkSelector(index_range=(0, 4))
        
        result = await generate_embeddings(
            db=AsyncMock(),
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=selector,
            openai_api_key="test-key",
            job_repo=job_repo,
            event_repo=event_repo,
            chunk_repo=chunk_repo,
            embedding_repo=embedding_repo,
        )
    
    # Total chunks = 10 (todos los chunks del archivo)
    # Embedded = 5 (solo chunks 0-4)
    # Skipped = 5 (chunks 5-9)
    assert result.total_chunks == 10
    assert result.embedded == 5
    assert result.skipped == 5


@pytest.mark.asyncio
async def test_generate_embeddings_with_index_range_middle(sample_chunks_for_range):
    """Test generación de embeddings con index_range en medio (3-6)."""
    job_id = uuid4()
    file_id = sample_chunks_for_range[0].file_id
    
    # Mock repositories
    from app.modules.rag.repositories import (
        RagJobRepository,
        RagJobEventRepository,
        ChunkMetadataRepository,
        DocumentEmbeddingRepository,
    )
    
    job_repo = Mock(spec=RagJobRepository)
    event_repo = Mock(spec=RagJobEventRepository)
    event_repo.log_event = AsyncMock()
    
    chunk_repo = Mock(spec=ChunkMetadataRepository)
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks_for_range)
    
    embedding_repo = Mock(spec=DocumentEmbeddingRepository)
    embedding_repo.exists_for_file_and_chunk = AsyncMock(return_value=False)
    embedding_repo.insert_embeddings = AsyncMock(
        side_effect=lambda db, embs: embs
    )
    
    # Mock OpenAI embeddings function
    with patch(
        'app.modules.rag.facades.embed_facade.openai_generate_embeddings',
        new=AsyncMock(return_value=[[0.1] * 1536 for _ in range(4)])
    ):
        selector = ChunkSelector(index_range=(3, 6))
        
        result = await generate_embeddings(
            db=AsyncMock(),
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=selector,
            openai_api_key="test-key",
            job_repo=job_repo,
            event_repo=event_repo,
            chunk_repo=chunk_repo,
            embedding_repo=embedding_repo,
        )
    
    # Total chunks = 10
    # Embedded = 4 (chunks 3, 4, 5, 6)
    # Skipped = 6 (chunks 0-2, 7-9)
    assert result.total_chunks == 10
    assert result.embedded == 4
    assert result.skipped == 6


@pytest.mark.asyncio
async def test_generate_embeddings_with_index_range_single(sample_chunks_for_range):
    """Test generación de embeddings con index_range de un solo chunk (5-5)."""
    job_id = uuid4()
    file_id = sample_chunks_for_range[0].file_id
    
    # Mock repositories
    from app.modules.rag.repositories import (
        RagJobRepository,
        RagJobEventRepository,
        ChunkMetadataRepository,
        DocumentEmbeddingRepository,
    )
    
    job_repo = Mock(spec=RagJobRepository)
    event_repo = Mock(spec=RagJobEventRepository)
    event_repo.log_event = AsyncMock()
    
    chunk_repo = Mock(spec=ChunkMetadataRepository)
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks_for_range)
    
    embedding_repo = Mock(spec=DocumentEmbeddingRepository)
    embedding_repo.exists_for_file_and_chunk = AsyncMock(return_value=False)
    embedding_repo.insert_embeddings = AsyncMock(
        side_effect=lambda db, embs: embs
    )
    
    # Mock OpenAI embeddings function
    with patch(
        'app.modules.rag.facades.embed_facade.openai_generate_embeddings',
        new=AsyncMock(return_value=[[0.1] * 1536])
    ):
        selector = ChunkSelector(index_range=(5, 5))
        
        result = await generate_embeddings(
            db=AsyncMock(),
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=selector,
            openai_api_key="test-key",
            job_repo=job_repo,
            event_repo=event_repo,
            chunk_repo=chunk_repo,
            embedding_repo=embedding_repo,
        )
    
    # Total chunks = 10
    # Embedded = 1 (solo chunk 5)
    # Skipped = 9
    assert result.total_chunks == 10
    assert result.embedded == 1
    assert result.skipped == 9


@pytest.mark.asyncio
async def test_generate_embeddings_with_index_range_out_of_bounds(sample_chunks_for_range):
    """Test generación con index_range fuera de rango (15-20)."""
    job_id = uuid4()
    file_id = sample_chunks_for_range[0].file_id
    
    # Mock repositories
    from app.modules.rag.repositories import (
        RagJobRepository,
        RagJobEventRepository,
        ChunkMetadataRepository,
        DocumentEmbeddingRepository,
    )
    
    job_repo = Mock(spec=RagJobRepository)
    event_repo = Mock(spec=RagJobEventRepository)
    event_repo.log_event = AsyncMock()
    
    chunk_repo = Mock(spec=ChunkMetadataRepository)
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks_for_range)
    
    embedding_repo = Mock(spec=DocumentEmbeddingRepository)
    
    # Mock OpenAI embeddings function (no debería ser llamado)
    with patch(
        'app.modules.rag.facades.embed_facade.openai_generate_embeddings',
        new=AsyncMock(return_value=[])
    ):
        selector = ChunkSelector(index_range=(15, 20))
        
        result = await generate_embeddings(
            db=AsyncMock(),
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=selector,
            openai_api_key="test-key",
            job_repo=job_repo,
            event_repo=event_repo,
            chunk_repo=chunk_repo,
            embedding_repo=embedding_repo,
        )
    
    # Total chunks = 10
    # Embedded = 0 (ningún chunk en rango 15-20)
    # Skipped = 10
    assert result.total_chunks == 10
    assert result.embedded == 0
    assert result.skipped == 10
