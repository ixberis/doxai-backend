
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_ocr_facade_integration.py

Tests de integración para ocr_facade con mocks de Azure y storage.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 2)
"""

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.facades.ocr_facade import run_ocr, OcrText
from app.modules.rag.repositories import RagJobRepository, RagJobEventRepository
from app.modules.rag.enums import RagPhase, OcrOptimization
from app.shared.integrations.azure_document_intelligence import AzureOcrResult


@pytest.fixture
def mock_azure_client():
    """Mock del cliente de Azure Document Intelligence."""
    client = Mock()

    # Simular resultado exitoso de OCR
    async def mock_analyze(*args, **kwargs):
        return AzureOcrResult(
            text="Extracted text from scanned document",
            pages=[
                {"page_number": 1, "width": 612, "height": 792, "unit": "pixel"},
            ],
            confidence=0.95,
            lang="en-US",
            model_used="prebuilt-read",
        )

    client.analyze_document = AsyncMock(side_effect=mock_analyze)
    return client


@pytest.fixture
def mock_storage_client():
    """Mock del cliente de storage."""
    client = Mock()
    client.write = AsyncMock(return_value="rag-cache-pages/test-job/ocr_result.txt")
    return client


@pytest.fixture
def mock_repositories():
    """Mock de repositories."""
    job_repo = Mock(spec=RagJobRepository)
    event_repo = Mock(spec=RagJobEventRepository)
    event_repo.log_event = AsyncMock()
    return job_repo, event_repo


@pytest.mark.asyncio
async def test_run_ocr_success(
    adb: AsyncSession,
    mock_azure_client,
    mock_storage_client,
    mock_repositories,
):
    """Debe ejecutar OCR exitosamente con Azure."""
    job_id = uuid4()
    file_id = uuid4()
    source_uri = "https://example.com/scanned.pdf"

    job_repo, event_repo = mock_repositories

    result = await run_ocr(
        db=adb,
        job_id=job_id,
        file_id=file_id,
        source_uri=source_uri,
        strategy=OcrOptimization.balanced,
        azure_client=mock_azure_client,
        storage_client=mock_storage_client,
        job_repo=job_repo,
        event_repo=event_repo,
    )

    # Validar resultado
    assert isinstance(result, OcrText)
    assert result.result_uri.startswith("rag-cache-pages/")
    assert result.confidence == 0.95
    assert result.lang == "en-US"

    # Validar que se llamó a Azure
    mock_azure_client.analyze_document.assert_called_once()
    call_kwargs = mock_azure_client.analyze_document.call_args.kwargs
    assert call_kwargs["file_uri"] == source_uri
    assert call_kwargs["strategy"] == "balanced"

    # Validar que se guardó en storage
    mock_storage_client.write.assert_called_once()

    # Validar eventos (inicio y fin)
    assert event_repo.log_event.call_count == 2

    # Evento de inicio
    first_call = event_repo.log_event.call_args_list[0]
    assert first_call.kwargs["event_type"] == "phase_started"
    assert first_call.kwargs["rag_phase"] == RagPhase.ocr

    # Evento de fin
    last_call = event_repo.log_event.call_args_list[1]
    assert last_call.kwargs["event_type"] == "phase_completed"
    assert last_call.kwargs["rag_phase"] == RagPhase.ocr
    assert last_call.kwargs["progress_pct"] == 100


@pytest.mark.asyncio
async def test_run_ocr_azure_client_required(
    adb: AsyncSession,
    mock_storage_client,
):
    """Debe requerir azure_client."""
    job_id = uuid4()
    file_id = uuid4()

    with pytest.raises(RuntimeError) as exc_info:
        await run_ocr(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            source_uri="https://example.com/doc.pdf",
            azure_client=None,  # Sin cliente
            storage_client=mock_storage_client,
        )

    assert "azure_client is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_ocr_storage_client_required(
    adb: AsyncSession,
    mock_azure_client,
):
    """Debe requerir storage_client."""
    job_id = uuid4()
    file_id = uuid4()

    with pytest.raises(RuntimeError) as exc_info:
        await run_ocr(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            source_uri="https://example.com/doc.pdf",
            azure_client=mock_azure_client,
            storage_client=None,  # Sin cliente
        )

    assert "storage_client is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_ocr_strategy_normalization(
    adb: AsyncSession,
    mock_azure_client,
    mock_storage_client,
    mock_repositories,
):
    """Debe normalizar strategy string a enum."""
    job_id = uuid4()
    file_id = uuid4()
    job_repo, event_repo = mock_repositories

    # Pasar strategy como string
    result = await run_ocr(
        db=adb,
        job_id=job_id,
        file_id=file_id,
        source_uri="https://example.com/doc.pdf",
        strategy="fast",  # String en lugar de enum
        azure_client=mock_azure_client,
        storage_client=mock_storage_client,
        job_repo=job_repo,
        event_repo=event_repo,
    )

    assert isinstance(result, OcrText)

    # Verificar que se llamó con la estrategia correcta
    call_kwargs = mock_azure_client.analyze_document.call_args.kwargs
    assert call_kwargs["strategy"] == "fast"


@pytest.mark.asyncio
async def test_run_ocr_invalid_strategy(
    adb: AsyncSession,
    mock_azure_client,
    mock_storage_client,
):
    """Debe lanzar ValueError para estrategia inválida."""
    job_id = uuid4()
    file_id = uuid4()

    with pytest.raises(ValueError) as exc_info:
        await run_ocr(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            source_uri="https://example.com/doc.pdf",
            strategy="invalid_strategy",
            azure_client=mock_azure_client,
            storage_client=mock_storage_client,
        )

    assert "Estrategia OCR inválida" in str(exc_info.value)


@pytest.mark.asyncio
async def test_run_ocr_azure_error_handling(
    adb: AsyncSession,
    mock_storage_client,
    mock_repositories,
):
    """Debe manejar errores de Azure y registrar evento de fallo."""
    job_id = uuid4()
    file_id = uuid4()
    job_repo, event_repo = mock_repositories

    # Mock que lanza error
    azure_client_error = Mock()
    azure_client_error.analyze_document = AsyncMock(
        side_effect=RuntimeError("Azure API error")
    )

    with pytest.raises(RuntimeError) as exc_info:
        await run_ocr(
            db=adb,
            job_id=job_id,
            file_id=file_id,
            source_uri="https://example.com/doc.pdf",
            azure_client=azure_client_error,
            storage_client=mock_storage_client,
            job_repo=job_repo,
            event_repo=event_repo,
        )

    assert "Error en OCR" in str(exc_info.value)

    # Debe haber registrado evento de fallo
    last_call = event_repo.log_event.call_args_list[-1]
    assert last_call.kwargs["event_type"] == "phase_failed"
    assert last_call.kwargs["rag_phase"] == RagPhase.ocr
