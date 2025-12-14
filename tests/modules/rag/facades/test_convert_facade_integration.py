# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_convert_facade_integration.py

Tests de integración para convert_facade con mocks de storage.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 2)
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.facades.convert_facade import convert_to_text, ConvertedText
from app.modules.rag.repositories import RagJobRepository, RagJobEventRepository
from app.modules.rag.enums import RagPhase


@pytest.fixture
def mock_storage_client():
    """Mock del cliente de storage."""
    client = Mock()
    client.read = AsyncMock(return_value=b"Sample text content from document")
    client.write = AsyncMock(return_value="rag-cache-jobs/test-job/converted.txt")
    return client


@pytest.fixture
def mock_repositories():
    """Mock de repositories."""
    job_repo = Mock(spec=RagJobRepository)
    event_repo = Mock(spec=RagJobEventRepository)
    event_repo.log_event = AsyncMock()
    return job_repo, event_repo


@pytest.mark.asyncio
async def test_convert_to_text_plain_text_success(
    adb: AsyncSession,
    mock_storage_client,
    mock_repositories,
):
    """Debe extraer texto plano exitosamente."""
    job_id = uuid4()
    file_id = uuid4()
    source_uri = "users-files/test.txt"
    
    job_repo, event_repo = mock_repositories
    
    result = await convert_to_text(
        db=adb,
        job_id=job_id,
        file_id=file_id,
        source_uri=source_uri,
        mime_type="text/plain",
        storage_client=mock_storage_client,
        job_repo=job_repo,
        event_repo=event_repo,
    )
    
    # Validar resultado
    assert isinstance(result, ConvertedText)
    assert result.result_uri.startswith("rag-cache-jobs/")
    assert result.byte_size > 0
    assert len(result.checksum) == 64  # SHA-256 hex
    
    # Validar que se llamó al storage
    mock_storage_client.read.assert_called_once_with(source_uri)
    mock_storage_client.write.assert_called_once()
    
    # Validar eventos registrados (inicio y fin)
    assert event_repo.log_event.call_count == 2
    
    # Primer evento: phase_started
    first_call = event_repo.log_event.call_args_list[0]
    assert first_call.kwargs["event_type"] == "phase_started"
    assert first_call.kwargs["rag_phase"] == RagPhase.convert
    
    # Segundo evento: phase_completed
    second_call = event_repo.log_event.call_args_list[1]
    assert second_call.kwargs["event_type"] == "phase_completed"
    assert second_call.kwargs["rag_phase"] == RagPhase.convert


@pytest.mark.asyncio
async def test_convert_to_text_unsupported_mime_type(
    adb: AsyncSession,
    mock_storage_client,
    mock_repositories,
):
    """Debe lanzar ValueError para mime types no soportados."""
    job_id = uuid4()
    file_id = uuid4()
    job_repo, event_repo = mock_repositories
    
    with pytest.raises(RuntimeError) as exc_info:
        await convert_to_text(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            source_uri="users-files/doc.pdf",
            mime_type="application/pdf",  # No implementado aún
            storage_client=mock_storage_client,
            job_repo=job_repo,
            event_repo=event_repo,
        )
    
    # NotImplementedError se propaga sin envolver (contrato de fase no implementada)
    assert "PDF text extraction requires PyPDF2" in str(exc_info.value)
    
    # NotImplementedError no registra evento phase_failed (se propaga directamente)
    # Solo debe haber registrado phase_started
    assert event_repo.log_event.call_count == 1
    assert event_repo.log_event.call_args_list[0].kwargs["event_type"] == "phase_started"


@pytest.mark.asyncio
async def test_convert_to_text_storage_client_required(
    adb: AsyncSession,
):
    """Debe requerir storage_client."""
    job_id = uuid4()
    file_id = uuid4()
    
    with pytest.raises(RuntimeError) as exc_info:
        await convert_to_text(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            source_uri="users-files/test.txt",
            mime_type="text/plain",
            storage_client=None,  # Sin cliente
        )
    
    assert "storage_client is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_convert_to_text_markdown_success(
    adb: AsyncSession,
    mock_storage_client,
    mock_repositories,
):
    """Debe extraer markdown exitosamente."""
    job_id = uuid4()
    file_id = uuid4()
    
    # Simular contenido markdown
    mock_storage_client.read.return_value = b"# Title\\n\\nSome markdown content"
    
    job_repo, event_repo = mock_repositories
    
    result = await convert_to_text(
        db=adb,
        job_id=job_id,
        file_id=file_id,
        source_uri="users-files/doc.md",
        mime_type="text/markdown",
        storage_client=mock_storage_client,
        job_repo=job_repo,
        event_repo=event_repo,
    )
    
    assert isinstance(result, ConvertedText)
    assert result.byte_size > 0
    
    # Validar que se completó la fase
    last_event = event_repo.log_event.call_args_list[-1]
    assert last_event.kwargs["event_type"] == "phase_completed"
    assert last_event.kwargs["progress_pct"] == 100
