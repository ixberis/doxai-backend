# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_embed_facade_integration.py

Tests de integración para embed_facade con mocks de OpenAI y repositories.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 2)
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.facades.embed_facade import (
    generate_embeddings,
    ChunkSelector,
    EmbeddingResult,
)
from app.modules.rag.repositories import (
    RagJobRepository,
    RagJobEventRepository,
    ChunkMetadataRepository,
    DocumentEmbeddingRepository,
)
from app.modules.rag.models import ChunkMetadata
from app.modules.rag.enums import RagPhase


@pytest.fixture
def mock_repositories():
    """Mock de repositories."""
    job_repo = Mock(spec=RagJobRepository)
    event_repo = Mock(spec=RagJobEventRepository)
    event_repo.log_event = AsyncMock()
    
    chunk_repo = Mock(spec=ChunkMetadataRepository)
    embedding_repo = Mock(spec=DocumentEmbeddingRepository)
    embedding_repo.exists_for_file_and_chunk = AsyncMock(return_value=False)
    embedding_repo.insert_embeddings = AsyncMock(return_value=[Mock(), Mock()])
    
    return job_repo, event_repo, chunk_repo, embedding_repo


@pytest.fixture
def sample_chunks():
    """Chunks de ejemplo para tests."""
    file_id = uuid4()
    return [
        ChunkMetadata(
            chunk_id=uuid4(),
            file_id=file_id,
            chunk_index=0,
            chunk_text="First chunk of text",
            token_count=5,
            source_page_start=1,
            source_page_end=1,
        ),
        ChunkMetadata(
            chunk_id=uuid4(),
            file_id=file_id,
            chunk_index=1,
            chunk_text="Second chunk of text",
            token_count=5,
            source_page_start=1,
            source_page_end=1,
        ),
    ]


@pytest.mark.asyncio
async def test_generate_embeddings_success(
    adb: AsyncSession,
    mock_repositories,
    sample_chunks,
):
    """Debe generar embeddings exitosamente."""
    job_id = uuid4()
    file_id = sample_chunks[0].file_id
    
    job_repo, event_repo, chunk_repo, embedding_repo = mock_repositories
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks)
    
    # Mock de OpenAI embeddings client (usar el alias importado en facade)
    mock_vectors = [[0.1] * 1536, [0.2] * 1536]
    
    with patch(
        "app.modules.rag.facades.embed_facade.openai_generate_embeddings",
        new_callable=AsyncMock,
        return_value=mock_vectors,
    ):
        result = await generate_embeddings(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=ChunkSelector(),  # Sin selector: todos los chunks
            openai_api_key="sk-test-key",
            job_repo=job_repo,
            event_repo=event_repo,
            chunk_repo=chunk_repo,
            embedding_repo=embedding_repo,
        )
    
    # Validar resultado
    assert isinstance(result, EmbeddingResult)
    assert result.total_chunks == 2
    assert result.embedded == 2
    assert result.skipped == 0
    
    # Validar que se llamó al chunk_repo
    chunk_repo.list_by_file.assert_called_once_with(adb, file_id)
    
    # Validar que se insertaron embeddings
    embedding_repo.insert_embeddings.assert_called_once()
    
    # Validar eventos (inicio y fin)
    assert event_repo.log_event.call_count == 2
    
    # Evento de inicio
    first_call = event_repo.log_event.call_args_list[0]
    assert first_call.kwargs["event_type"] == "phase_started"
    assert first_call.kwargs["rag_phase"] == RagPhase.embed
    
    # Evento de fin
    last_call = event_repo.log_event.call_args_list[1]
    assert last_call.kwargs["event_type"] == "phase_completed"
    assert last_call.kwargs["progress_pct"] == 100


@pytest.mark.asyncio
async def test_generate_embeddings_with_selector_by_ids(
    adb: AsyncSession,
    mock_repositories,
    sample_chunks,
):
    """Debe generar embeddings solo para chunks seleccionados por ID."""
    job_id = uuid4()
    file_id = sample_chunks[0].file_id
    
    job_repo, event_repo, chunk_repo, embedding_repo = mock_repositories
    
    # Mock para get_by_id: solo devuelve el primer chunk
    chunk_repo.get_by_id = AsyncMock(return_value=sample_chunks[0])
    
    # Configurar insert_embeddings para devolver solo 1 embedding (no 2 como el default)
    embedding_repo.insert_embeddings = AsyncMock(return_value=[Mock()])
    
    selector = ChunkSelector(chunk_ids=[sample_chunks[0].chunk_id])
    
    mock_vectors = [[0.1] * 1536]
    
    with patch(
        "app.modules.rag.facades.embed_facade.openai_generate_embeddings",
        new_callable=AsyncMock,
        return_value=mock_vectors,
    ):
        result = await generate_embeddings(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=selector,
            openai_api_key="sk-test-key",
            job_repo=job_repo,
            event_repo=event_repo,
            chunk_repo=chunk_repo,
            embedding_repo=embedding_repo,
        )
    
    assert result.total_chunks == 1
    assert result.embedded == 1


@pytest.mark.asyncio
async def test_generate_embeddings_with_index_range(
    adb: AsyncSession,
    mock_repositories,
    sample_chunks,
):
    """Debe generar embeddings solo para chunks en rango de índices."""
    job_id = uuid4()
    file_id = sample_chunks[0].file_id
    
    job_repo, event_repo, chunk_repo, embedding_repo = mock_repositories
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks)
    
    # Configurar insert_embeddings para devolver solo 1 embedding
    embedding_repo.insert_embeddings = AsyncMock(return_value=[Mock()])
    
    # Selector: solo chunk_index 0
    selector = ChunkSelector(index_range=(0, 0))
    
    mock_vectors = [[0.1] * 1536]
    
    with patch(
        "app.modules.rag.facades.embed_facade.openai_generate_embeddings",
        new_callable=AsyncMock,
        return_value=mock_vectors,
    ):
        result = await generate_embeddings(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=selector,
            openai_api_key="sk-test-key",
            job_repo=job_repo,
            event_repo=event_repo,
            chunk_repo=chunk_repo,
            embedding_repo=embedding_repo,
        )
    
    # total_chunks debe reflejar todos los chunks del archivo (aquí 2),
    # mientras que embedded refleja solo los chunks dentro del rango (1)
    assert result.total_chunks == 2
    assert result.embedded == 1


@pytest.mark.asyncio
async def test_generate_embeddings_idempotency(
    adb: AsyncSession,
    mock_repositories,
    sample_chunks,
):
    """Debe saltar chunks que ya tienen embeddings (idempotencia)."""
    job_id = uuid4()
    file_id = sample_chunks[0].file_id
    
    job_repo, event_repo, chunk_repo, embedding_repo = mock_repositories
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks)
    
    # Mock: todos los chunks ya tienen embeddings
    embedding_repo.exists_for_file_and_chunk = AsyncMock(return_value=True)
    
    result = await generate_embeddings(
        db=adb,
        job_id=job_id,
        file_id=file_id,
        embedding_model="text-embedding-3-large",
        selector=ChunkSelector(),
        openai_api_key="sk-test-key",
        job_repo=job_repo,
        event_repo=event_repo,
        chunk_repo=chunk_repo,
        embedding_repo=embedding_repo,
    )
    
    assert result.total_chunks == 2
    assert result.embedded == 0
    assert result.skipped == 2
    
    # No debe haber llamado a insert_embeddings
    embedding_repo.insert_embeddings.assert_not_called()


@pytest.mark.asyncio
async def test_generate_embeddings_openai_key_required(
    adb: AsyncSession,
):
    """Debe requerir openai_api_key."""
    job_id = uuid4()
    file_id = uuid4()
    
    with pytest.raises(RuntimeError) as exc_info:
        await generate_embeddings(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            embedding_model="text-embedding-3-large",
            selector=ChunkSelector(),
            openai_api_key=None,  # Sin API key
        )
    
    assert "openai_api_key is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_generate_embeddings_no_chunks_found(
    adb: AsyncSession,
    mock_repositories,
):
    """Debe manejar caso de no encontrar chunks."""
    job_id = uuid4()
    file_id = uuid4()
    
    job_repo, event_repo, chunk_repo, embedding_repo = mock_repositories
    chunk_repo.list_by_file = AsyncMock(return_value=[])  # Sin chunks
    
    result = await generate_embeddings(
        db=adb,
        job_id=job_id,
        file_id=file_id,
        embedding_model="text-embedding-3-large",
        selector=ChunkSelector(),
        openai_api_key="sk-test-key",
        job_repo=job_repo,
        event_repo=event_repo,
        chunk_repo=chunk_repo,
        embedding_repo=embedding_repo,
    )
    
    assert result.total_chunks == 0
    assert result.embedded == 0
    assert result.skipped == 0


@pytest.mark.asyncio
async def test_generate_embeddings_openai_error_handling(
    adb: AsyncSession,
    mock_repositories,
    sample_chunks,
):
    """Debe manejar errores de OpenAI y registrar evento de fallo."""
    job_id = uuid4()
    file_id = sample_chunks[0].file_id
    
    job_repo, event_repo, chunk_repo, embedding_repo = mock_repositories
    chunk_repo.list_by_file = AsyncMock(return_value=sample_chunks)
    
    # Mock que lanza error desde OpenAI client (usar el alias del facade)
    with patch(
        "app.modules.rag.facades.embed_facade.openai_generate_embeddings",
        new_callable=AsyncMock,
        side_effect=RuntimeError("OpenAI API error"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            await generate_embeddings(
                db=adb,
                job_id=job_id,
                file_id=file_id,
                embedding_model="text-embedding-3-large",
                selector=ChunkSelector(),
                openai_api_key="sk-test-key",
                job_repo=job_repo,
                event_repo=event_repo,
                chunk_repo=chunk_repo,
                embedding_repo=embedding_repo,
            )
    
    assert "Error en generación de embeddings" in str(exc_info.value)
    
    # Debe haber registrado evento de fallo
    last_call = event_repo.log_event.call_args_list[-1]
    assert last_call.kwargs["event_type"] == "phase_failed"
    assert last_call.kwargs["rag_phase"] == RagPhase.embed
