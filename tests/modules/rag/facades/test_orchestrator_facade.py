# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_orchestrator_facade.py

Tests de integración para orchestrator_facade con mocks de Payments.

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 3)
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from app.modules.rag.facades.orchestrator_facade import run_indexing_job, OrchestrationSummary
from app.modules.rag.enums import RagJobPhase, RagPhase


@pytest.mark.asyncio
async def test_orchestrator_pipeline_success(adb):
    """Test: Pipeline completo ejecuta todas las fases y consume créditos."""
    
    project_id = uuid4()
    file_id = uuid4()
    user_id = uuid4()
    
    # Crear proyecto en DB para satisfacer FK constraint
    from app.modules.projects.models.project_models import Project
    from app.modules.projects.enums.project_state_enum import ProjectState
    
    project = Project(
        id=project_id,
        user_id=user_id,
        user_email="test@example.com",
        project_name="Test Project",
        project_slug=f"test-project-{project_id}",
        state=ProjectState.created,
    )
    adb.add(project)
    await adb.flush()
    
    # Crear InputFile para satisfacer FK constraint en files_base
    from app.modules.files.models.input_file_models import InputFile
    from app.modules.files.enums import FileType
    
    input_file = InputFile(
        input_file_id=file_id,
        project_id=project_id,
        input_file_uploaded_by=user_id,
        input_file_original_name="test.pdf",
        input_file_mime_type="application/pdf",
        input_file_size_bytes=1024,
        input_file_type=FileType.document,
        input_file_storage_path="users-files/test.pdf",
    )
    adb.add(input_file)
    await adb.flush()
    
    # Refrescar el objeto para obtener el file_id asignado por el trigger de BD
    await adb.refresh(input_file)
    file_id = input_file.file_id
    
    # Mock storage client
    mock_storage = AsyncMock()
    mock_storage.download_file.return_value = b"Sample text for chunking and embeddings"
    mock_storage.upload_file.return_value = "rag-cache-jobs/test.txt"
    
    # Mock Azure OCR client
    mock_azure = AsyncMock()
    mock_azure.analyze_document.return_value = SimpleNamespace(
        result_uri="rag-cache-pages/ocr_result.txt",
        total_pages=1,
    )
    
    # Mock OpenAI embeddings
    mock_openai = AsyncMock()
    mock_openai.return_value = [[0.1] * 1536]  # embedding vector
    
    # Mock Payments services
    mock_wallet = SimpleNamespace(wallet_id=1, user_id=user_id, balance_total=1000)
    mock_reservation = SimpleNamespace(
        reservation_id=1,
        wallet_id=1,
        credits_reserved=50,
        operation_id="rag_job_test",
    )
    
    with patch('app.modules.rag.facades.orchestrator_facade.ReservationService') as MockReservation, \
         patch('app.modules.rag.facades.orchestrator_facade.WalletService') as MockWallet, \
         patch('app.modules.rag.facades.convert_facade.convert_to_text') as mock_convert, \
         patch('app.modules.rag.facades.ocr_facade.run_ocr') as mock_ocr, \
         patch('app.modules.rag.facades.embed_facade.generate_embeddings') as mock_embed, \
         patch('app.shared.integrations.openai_embeddings_client.generate_embeddings', mock_openai):
        
        # Setup mocks
        mock_reservation_service = MockReservation.return_value
        mock_reservation_service.create_reservation = AsyncMock(return_value=mock_reservation)
        mock_reservation_service.consume_reservation = AsyncMock(return_value=mock_reservation)
        mock_reservation_service.cancel_reservation = AsyncMock(return_value=mock_reservation)
        
        mock_wallet_service = MockWallet.return_value
        
        # Mock facades
        mock_convert.return_value = SimpleNamespace(result_uri="rag-cache-jobs/converted.txt")
        mock_ocr.return_value = SimpleNamespace(result_uri="rag-cache-pages/ocr.txt", total_pages=1)
        mock_embed.return_value = SimpleNamespace(total_embeddings=5, embedding_ids=[uuid4() for _ in range(5)])
        
        # Execute pipeline
        summary = await run_indexing_job(
            db=adb,
            project_id=project_id,
            file_id=file_id,
            user_id=user_id,
            mime_type="application/pdf",
            needs_ocr=True,
            storage_client=mock_storage,
            source_uri="users-files/test.pdf",
        )
        
        # Assertions
        assert summary.job_status == RagJobPhase.completed
        assert RagPhase.convert in summary.phases_done
        assert RagPhase.ocr in summary.phases_done
        assert RagPhase.chunk in summary.phases_done
        assert RagPhase.embed in summary.phases_done
        assert RagPhase.integrate in summary.phases_done
        assert RagPhase.ready in summary.phases_done
        assert summary.total_chunks > 0
        assert summary.total_embeddings > 0
        assert summary.credits_used > 0
        assert summary.reservation_id is not None
        
        # Verify Payments integration
        mock_reservation_service.create_reservation.assert_called_once()
        mock_reservation_service.consume_reservation.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_pipeline_failure_releases_credits(adb):
    """Test: Fallo en pipeline libera la reserva de créditos."""
    
    project_id = uuid4()
    file_id = uuid4()
    user_id = uuid4()
    
    # Crear proyecto en DB para satisfacer FK constraint
    from app.modules.projects.models.project_models import Project
    from app.modules.projects.enums.project_state_enum import ProjectState
    
    project = Project(
        id=project_id,
        user_id=user_id,
        user_email="test@example.com",
        project_name="Test Project Fail",
        project_slug=f"test-project-fail-{project_id}",
        state=ProjectState.created,
    )
    adb.add(project)
    await adb.flush()
    
    # Crear InputFile para satisfacer FK constraint en files_base
    from app.modules.files.models.input_file_models import InputFile
    from app.modules.files.enums import FileType
    
    input_file = InputFile(
        input_file_id=file_id,
        project_id=project_id,
        input_file_uploaded_by=user_id,
        input_file_original_name="test-fail.pdf",
        input_file_mime_type="application/pdf",
        input_file_size_bytes=1024,
        input_file_type=FileType.document,
        input_file_storage_path="users-files/test-fail.pdf",
    )
    adb.add(input_file)
    await adb.flush()
    
    # Refrescar el objeto para obtener el file_id asignado por el trigger de BD
    await adb.refresh(input_file)
    file_id = input_file.file_id
    
    # Mock storage client
    mock_storage = AsyncMock()
    mock_storage.download_file.side_effect = Exception("Storage error")
    
    # Mock Payments services
    mock_wallet = SimpleNamespace(wallet_id=1, user_id=user_id, balance_total=1000)
    mock_reservation = SimpleNamespace(
        reservation_id=1,
        wallet_id=1,
        credits_reserved=50,
        operation_id="rag_job_test",
    )
    
    with patch('app.modules.rag.facades.orchestrator_facade.ReservationService') as MockReservation, \
         patch('app.modules.rag.facades.orchestrator_facade.WalletService') as MockWallet:
        
        # Setup mocks
        mock_reservation_service = MockReservation.return_value
        mock_reservation_service.create_reservation = AsyncMock(return_value=mock_reservation)
        mock_reservation_service.cancel_reservation = AsyncMock(return_value=mock_reservation)
        
        mock_wallet_service = MockWallet.return_value
        
        # Execute pipeline (expect failure)
        summary = await run_indexing_job(
            db=adb,
            project_id=project_id,
            file_id=file_id,
            user_id=user_id,
            mime_type="application/pdf",
            needs_ocr=False,
            storage_client=mock_storage,
            source_uri="users-files/test.pdf",
        )
        
        # Assertions
        assert summary.job_status == RagJobPhase.failed
        assert summary.credits_used == 0
        
        # Verify reservation was released
        mock_reservation_service.cancel_reservation.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_fails_before_job_creation(adb):
    """Test FASE C: Fallo antes de crear job lanza RuntimeError sin job_id artificial."""
    
    project_id = uuid4()
    file_id = uuid4()
    user_id = uuid4()
    
    # CASO A: Forzar error antes de job_repo.create() pasando storage_client=None
    # Esto causa ValueError en validación temprana (línea 154-155)
    
    with pytest.raises(ValueError, match="storage_client is required"):
        await run_indexing_job(
            db=adb,
            project_id=project_id,
            file_id=file_id,
            user_id=user_id,
            mime_type="application/pdf",
            needs_ocr=False,
            storage_client=None,  # Forzar fallo temprano
            source_uri="users-files/test.pdf",
        )
    
    # Verificar que NO se creó ningún job en DB para este proyecto/archivo
    from sqlalchemy import select
    from app.modules.rag.models.job_models import RagJob
    
    result = await adb.execute(
        select(RagJob).where(RagJob.project_id == project_id, RagJob.file_id == file_id)
    )
    jobs = result.scalars().all()
    assert len(jobs) == 0, "No job should be created for this file when validation fails early"


# Fin del archivo backend/tests/modules/rag/facades/test_orchestrator_facade.py
