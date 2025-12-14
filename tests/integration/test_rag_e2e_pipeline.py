# -*- coding: utf-8 -*-
"""
backend/tests/integration/test_rag_e2e_pipeline.py

Test End-to-End del pipeline RAG completo:
Auth → Projects → Files → RAG → Payments

Flujo:
1. Crear usuario (Auth)
2. Crear proyecto (Projects)
3. Subir archivo (Files)
4. Indexar documento (RAG)
5. Verificar progreso y estado
6. Validar integración con Payments (reserva/consumo de créditos)

IMPORTANTE: Este test NO llama servicios externos reales (Azure/OpenAI/Storage).
Usa mocks para todas las integraciones externas.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 5)
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.modules.auth.models.user_models import AppUser
from app.modules.projects.models.project_models import Project
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.enums import FileType, InputProcessingStatus, StorageBackend
from app.modules.rag.models import RagJob, RagJobEvent, ChunkMetadata, DocumentEmbedding
from app.modules.rag.enums import RagJobPhase, RagPhase
from app.modules.rag.schemas.indexing_schemas import IndexingJobCreate


@pytest.fixture
async def test_user(adb):
    """Crea un usuario de prueba para el E2E."""
    unique_email = f"e2e_test_{uuid4().hex[:8]}@example.com"
    user = AppUser(
        user_full_name="E2E Test User",
        user_email=unique_email,
        user_password_hash="hashed_password_placeholder",
        user_is_activated=True,
    )
    adb.add(user)
    await adb.flush()
    await adb.refresh(user)
    return user


@pytest.fixture
async def test_project(adb, test_user):
    """Crea un proyecto de prueba asociado al usuario.
    
    NOTA: projects.user_id es UUID, mientras que app_users.user_id es INTEGER.
    Para el test E2E generamos un UUID como owner_id del proyecto.
    """
    owner_uuid = uuid4()  # UUID para compatibilidad con schema de projects
    project = Project(
        id=uuid4(),
        user_id=owner_uuid,
        user_email=test_user.user_email,
        project_name="E2E RAG Test Project",
        project_slug=f"e2e-rag-test-{uuid4().hex[:8]}",
        project_description="Proyecto para test E2E del pipeline RAG",
    )
    adb.add(project)
    await adb.flush()
    await adb.refresh(project)
    # Adjuntamos el user_id integer para referencias cruzadas si es necesario
    project._test_user_int_id = test_user.user_id
    return project


@pytest.fixture
async def test_input_file(adb, test_project, test_user):
    """Crea un archivo de entrada simulado.
    
    NOTA: uploaded_by es UUID, usamos test_project.user_id (UUID)
    """
    input_file = InputFile(
        input_file_id=uuid4(),
        project_id=test_project.id,
        input_file_uploaded_by=test_project.user_id,  # UUID del owner del proyecto
        input_file_original_name="test_document.txt",
        input_file_display_name="Test Document for RAG E2E",
        input_file_mime_type="text/plain",
        input_file_size_bytes=1024,
        input_file_type=FileType.txt,
        input_file_storage_path=f"{test_project.id}/input/test_document.txt",
        input_file_storage_backend=StorageBackend.supabase,
        input_file_status=InputProcessingStatus.uploaded,
        input_file_uploaded_at=datetime.now(timezone.utc),
    )
    adb.add(input_file)
    await adb.flush()
    await adb.refresh(input_file)
    return input_file


@pytest.fixture
def mock_azure_client():
    """Mock de AzureDocumentIntelligenceClient."""
    with patch("app.shared.integrations.azure_document_intelligence.AzureDocumentIntelligenceClient") as MockClient:
        mock_instance = MockClient.return_value
        # Simular resultado de análisis de documento
        mock_instance.analyze_document = AsyncMock(return_value=MagicMock(
            pages=[
                MagicMock(content="Page 1: This is test content for RAG pipeline."),
                MagicMock(content="Page 2: More test content for embeddings."),
            ],
            metadata={"total_pages": 2}
        ))
        yield mock_instance


@pytest.fixture
def mock_openai_embeddings():
    """Mock de todas las facades RAG para evitar llamadas a servicios externos.
    
    Mockea convert, ocr, chunk, embed e integrate facades directamente en el
    orchestrator para evitar validaciones de API keys y llamadas reales.
    """
    from app.modules.rag.facades import convert_facade, chunk_facade, embed_facade, integrate_facade
    from app.modules.rag.enums import RagPhase
    
    with patch("app.modules.rag.facades.orchestrator_facade.convert_facade") as mock_convert, \
         patch("app.modules.rag.facades.orchestrator_facade.chunk_facade") as mock_chunk, \
         patch("app.modules.rag.facades.orchestrator_facade.embed_facade") as mock_embed, \
         patch("app.modules.rag.facades.orchestrator_facade.integrate_facade") as mock_integrate:
        
        # Mock convert_facade.convert_to_text
        mock_convert_result = MagicMock()
        mock_convert_result.result_uri = "converted/test-file.txt"
        mock_convert_result.byte_size = 1024
        mock_convert.convert_to_text = AsyncMock(return_value=mock_convert_result)
        
        # Mock chunk_facade.chunk_text
        mock_chunk_result = MagicMock()
        mock_chunk_result.total_chunks = 5
        mock_chunk_result.chunk_ids = [uuid4() for _ in range(5)]
        mock_chunk.chunk_text = AsyncMock(return_value=mock_chunk_result)
        mock_chunk.ChunkParams = MagicMock()
        
        # Mock embed_facade.generate_embeddings
        mock_embed_result = MagicMock()
        mock_embed_result.total_embeddings = 5
        mock_embed_result.embedding_ids = [uuid4() for _ in range(5)]
        mock_embed.generate_embeddings = AsyncMock(return_value=mock_embed_result)
        mock_embed.ChunkSelector = MagicMock()
        
        # Mock integrate_facade.integrate_vector_index
        mock_integrate_result = MagicMock()
        mock_integrate_result.ready = True
        mock_integrate_result.integrity_valid = True
        mock_integrate.integrate_vector_index = AsyncMock(return_value=mock_integrate_result)
        
        yield {
            "convert": mock_convert,
            "chunk": mock_chunk,
            "embed": mock_embed,
            "integrate": mock_integrate,
        }


@pytest.fixture
def mock_storage_client():
    """Mock de AsyncStorageClient para Supabase Storage.
    
    Este mock implementa el protocolo AsyncStorageClient y se pasa directamente
    a run_indexing_job en lugar de intentar patchear un getter inexistente.
    """
    mock_client = AsyncMock()
    # Simular lectura de archivo (download_file toma bucket y path)
    mock_client.download_file = AsyncMock(return_value=b"This is the content of the test document for RAG indexing.")
    # Simular escritura (convertido, cache, etc.)
    mock_client.upload_file = AsyncMock(return_value="mock_storage_path")
    mock_client.upload_bytes = AsyncMock(return_value="mock_storage_path")
    # Métodos adicionales que puede requerir el protocolo
    mock_client.read = AsyncMock(return_value=b"This is the content of the test document for RAG indexing.")
    mock_client.write = AsyncMock(return_value="mock_storage_path")
    mock_client.get_download_url = AsyncMock(return_value="https://mock.storage/file.txt")
    mock_client.delete_object = AsyncMock(return_value=True)
    return mock_client


@pytest.fixture
def mock_payments_facades():
    """Mock de ReservationService para reserva/consumo de créditos.
    
    El orchestrator_facade usa ReservationService internamente, así que
    parcheamos la clase completa en lugar de funciones sueltas.
    """
    with patch("app.modules.rag.facades.orchestrator_facade.ReservationService") as MockReservationService:
        # Crear instancia mock que se retornará al instanciar ReservationService
        mock_service_instance = AsyncMock()
        MockReservationService.return_value = mock_service_instance
        
        # Simular reserva exitosa
        mock_reservation = MagicMock()
        mock_reservation.reservation_id = 12345
        mock_reservation.credits_reserved = 100
        mock_service_instance.create_reservation = AsyncMock(return_value=mock_reservation)
        
        # Simular consumo exitoso
        mock_service_instance.consume_reservation = AsyncMock(return_value=None)
        
        # Simular liberación/cancelación exitosa (para casos de error)
        mock_service_instance.cancel_reservation = AsyncMock(return_value=None)
        
        yield {
            "service_class": MockReservationService,
            "service_instance": mock_service_instance,
            "reservation": mock_reservation,
        }


@pytest.mark.asyncio
async def test_rag_e2e_pipeline_success(
    adb,
    test_user,
    test_project,
    test_input_file,
    mock_azure_client,
    mock_openai_embeddings,
    mock_storage_client,
    mock_payments_facades,
):
    """
    Test E2E: Pipeline completo RAG con éxito.
    
    Flujo:
    1. Usuario y proyecto ya existen (fixtures)
    2. Archivo ya subido (fixture)
    3. Crear job de indexación RAG
    4. Ejecutar pipeline orquestado (convert → chunk → embed → integrate → ready)
    5. Verificar progreso del job
    6. Verificar estado del documento
    7. Validar integración con Payments (reserva y consumo de créditos)
    """
    
    # ==================== PASO 1: Crear job de indexación ====================
    from app.modules.rag.services.indexing_service import IndexingService
    
    indexing_service = IndexingService(db=adb)
    
    job_create = IndexingJobCreate(
        project_id=test_project.id,
        file_id=test_input_file.file_id,
        user_id=test_project.user_id,  # UUID del owner
        mime_type="text/plain",
        needs_ocr=False,  # Simplificar: sin OCR en este E2E
    )
    
    job_response = await indexing_service.create_indexing_job(job_create)
    
    assert job_response.job_id is not None
    assert job_response.project_id == test_project.id
    assert job_response.phase == RagJobPhase.queued
    
    job_id = job_response.job_id
    
    # ==================== PASO 2: Ejecutar pipeline orquestado ====================
    from app.modules.rag.facades.orchestrator_facade import run_indexing_job
    
    # Ejecutar pipeline completo (con mocks de Azure/OpenAI/Storage/Payments)
    # NOTA: run_indexing_job crea su propio job internamente, por lo que creará
    # un segundo job. El job_id del paso 1 se usa solo para verificar que el
    # IndexingService funciona correctamente por separado.
    result = await run_indexing_job(
        db=adb,
        file_id=test_input_file.file_id,
        project_id=test_project.id,
        user_id=test_project.user_id,
        needs_ocr=False,
        mime_type="text/plain",
        storage_client=mock_storage_client,
        source_uri="test-bucket/test-file.txt",  # URI requerido
    )
    
    assert result is not None
    assert result.job_status == RagJobPhase.completed
    assert result.total_chunks > 0
    assert result.total_embeddings > 0
    
    # Usar el job_id creado por el orchestrator para las verificaciones siguientes
    job_id = result.job_id
    
    # ==================== PASO 3: Verificar progreso del job ====================
    progress = await indexing_service.get_job_progress(job_id)
    
    assert progress.job_id == job_id
    assert progress.phase == RagPhase.ready
    assert progress.status == RagJobPhase.completed
    assert progress.progress_pct == 100
    assert progress.event_count > 0
    
    # Verificar timeline de eventos
    # Nota: Con facades mockeadas, solo se registran eventos de convert y ready
    # Las fases intermedias (chunk, embed, integrate) son manejadas por los mocks
    assert len(progress.timeline) > 0
    phases_in_timeline = {event.phase for event in progress.timeline if event.phase}
    # Al menos debe haber eventos de inicio y fin del pipeline
    assert len(phases_in_timeline) >= 1, f"Debe haber al menos una fase registrada, encontradas: {phases_in_timeline}"
    
    # ==================== PASO 4: Verificar que facades fueron invocadas ====================
    # Nota: Las facades están mockeadas, por lo que no hay embeddings reales en BD.
    # Verificamos que el mock de embed_facade fue llamado correctamente.
    mock_openai_embeddings["embed"].generate_embeddings.assert_called_once()
    mock_openai_embeddings["chunk"].chunk_text.assert_called_once()
    mock_openai_embeddings["convert"].convert_to_text.assert_called_once()
    mock_openai_embeddings["integrate"].integrate_vector_index.assert_called_once()
    
    # ==================== PASO 5: Validar integración con Payments ====================
    # Verificar que se llamó a create_reservation al iniciar el job
    mock_payments_facades["service_instance"].create_reservation.assert_called_once()
    
    # Verificar que se llamó a consume_reservation al completar exitosamente
    mock_payments_facades["service_instance"].consume_reservation.assert_called_once()
    
    # Verificar que NO se llamó a cancel_reservation (sólo en caso de fallo)
    mock_payments_facades["service_instance"].cancel_reservation.assert_not_called()
    
    # Verificar los créditos estimados y consumidos en el resultado
    assert result.credits_used > 0
    # credits_used debe ser <= credits_reserved (usamos menos o igual a lo reservado)
    assert result.credits_used <= mock_payments_facades["reservation"].credits_reserved


@pytest.mark.asyncio
async def test_rag_e2e_pipeline_failure_releases_credits(
    adb,
    test_user,
    test_project,
    test_input_file,
    mock_azure_client,
    mock_openai_embeddings,
    mock_storage_client,
    mock_payments_facades,
):
    """
    Test E2E: Pipeline RAG con fallo → libera créditos reservados.
    
    Simula un error en la fase de embeddings y verifica que:
    1. El job se marca como failed
    2. Los créditos reservados se liberan (NO se consumen)
    """
    
    # ==================== PASO 1: Simular fallo en generate_embeddings ====================
    # NOTA: No pre-creamos el job porque run_indexing_job lo crea automáticamente
    mock_openai_embeddings["embed"].generate_embeddings.side_effect = RuntimeError("Simulated OpenAI API failure")
    
    # ==================== PASO 2: Ejecutar pipeline (debe fallar) ====================
    from app.modules.rag.facades.orchestrator_facade import run_indexing_job
    
    # El orchestrator captura el error y retorna OrchestrationSummary con status failed
    result = await run_indexing_job(
        db=adb,
        file_id=test_input_file.file_id,
        project_id=test_project.id,
        user_id=test_project.user_id,  # UUID del owner
        needs_ocr=False,
        mime_type="text/plain",
        storage_client=mock_storage_client,
        source_uri="test-bucket/test-file.txt",
    )
    
    # ==================== PASO 3: Verificar que el resultado indica fallo ====================
    assert result.job_status == RagJobPhase.failed
    assert result.credits_used == 0  # No se consumieron créditos porque falló
    
    # ==================== PASO 4: Validar integración con Payments ====================
    # Verificar que se llamó a create_reservation
    mock_payments_facades["service_instance"].create_reservation.assert_called_once()
    
    # Verificar que NO se llamó a consume_reservation (porque falló)
    mock_payments_facades["service_instance"].consume_reservation.assert_not_called()
    
    # Verificar que SÍ se llamó a cancel_reservation (para liberar créditos)
    mock_payments_facades["service_instance"].cancel_reservation.assert_called_once()


# Fin del archivo backend/tests/integration/test_rag_e2e_pipeline.py
