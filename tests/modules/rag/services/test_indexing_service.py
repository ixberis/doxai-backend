# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/services/test_indexing_service.py

Tests para IndexingService - FASE 4.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 4)
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from app.modules.rag.services.indexing_service import IndexingService
from app.modules.rag.schemas.indexing_schemas import IndexingJobCreate
from app.modules.rag.enums import RagJobPhase, RagPhase
from app.modules.projects.enums import ProjectState


@pytest.mark.asyncio
async def test_create_indexing_job_success(adb):
    """Test: Crear job cuando proyecto existe y no está archivado."""
    
    project_id = uuid4()
    file_id = uuid4()
    user_id = uuid4()
    
    # Mock del proyecto
    mock_project = SimpleNamespace(
        project_id=project_id,
        project_is_archived=False,
        state=ProjectState.ready,
    )
    
    with patch.object(adb, "get", AsyncMock(return_value=mock_project)), \
         patch("app.modules.rag.services.indexing_service.rag_job_repository") as MockJobRepo, \
         patch("app.modules.rag.services.indexing_service.rag_job_event_repository") as MockEventRepo:
        
        # Mock repository responses
        mock_job = SimpleNamespace(
            job_id=uuid4(),
            project_id=project_id,
            file_id=file_id,
            created_by=user_id,
            phase=RagJobPhase.queued,
            status=RagJobPhase.queued,
            created_at="2025-11-28T10:00:00Z",
            updated_at="2025-11-28T10:00:00Z",
        )
        MockJobRepo.create = AsyncMock(return_value=mock_job)
        MockEventRepo.log_event = AsyncMock()
        
        # Execute
        service = IndexingService(adb)
        data = IndexingJobCreate(
            project_id=project_id,
            file_id=file_id,
            user_id=user_id,
            needs_ocr=False,
        )
        
        response = await service.create_indexing_job(data)
        
        # Assertions
        assert response.job_id == mock_job.job_id
        assert response.project_id == project_id
        assert response.started_by == user_id
        assert response.phase == RagJobPhase.queued
        
        MockJobRepo.create.assert_called_once()
        MockEventRepo.log_event.assert_called_once()


@pytest.mark.asyncio
async def test_create_indexing_job_project_not_found(adb):
    """Test: Error cuando proyecto no existe."""
    
    project_id = uuid4()
    file_id = uuid4()
    user_id = uuid4()
    
    with patch.object(adb, "get", AsyncMock(return_value=None)):
        service = IndexingService(adb)
        data = IndexingJobCreate(
            project_id=project_id,
            file_id=file_id,
            user_id=user_id,
            needs_ocr=False,
        )
        
        with pytest.raises(Exception) as exc_info:
            await service.create_indexing_job(data)
        
        assert "no encontrado" in str(exc_info.value).lower() or "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_indexing_job_project_archived(adb):
    """Test: Error cuando proyecto está archivado."""
    
    project_id = uuid4()
    file_id = uuid4()
    user_id = uuid4()
    
    # Mock del proyecto archivado
    mock_project = SimpleNamespace(
        project_id=project_id,
        project_is_archived=True,
        state=ProjectState.archived,
    )
    
    with patch.object(adb, "get", AsyncMock(return_value=mock_project)):
        service = IndexingService(adb)
        data = IndexingJobCreate(
            project_id=project_id,
            file_id=file_id,
            user_id=user_id,
            needs_ocr=False,
        )
        
        with pytest.raises(Exception) as exc_info:
            await service.create_indexing_job(data)
        
        assert "archivado" in str(exc_info.value).lower() or "400" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_job_progress_success(adb):
    """Test: Obtener progreso de job existente con timeline poblada."""
    
    job_id = uuid4()
    project_id = uuid4()
    
    file_id = uuid4()
    
    mock_job = SimpleNamespace(
        job_id=job_id,
        project_id=project_id,
        file_id=file_id,
        phase_current=RagPhase.embed,
        status=RagJobPhase.running,
        started_at="2025-11-28T10:00:00Z",
        completed_at=None,
        updated_at="2025-11-28T10:05:00Z",
    )
    
    mock_timeline = [
        SimpleNamespace(
            rag_phase=RagPhase.convert,
            message="Fase convert iniciada",
            progress_pct=20,
            created_at="2025-11-28T10:01:00Z",
        ),
        SimpleNamespace(
            rag_phase=RagPhase.chunk,
            message="Fase chunk completada",
            progress_pct=60,
            created_at="2025-11-28T10:03:00Z",
        ),
    ]
    
    with patch("app.modules.rag.services.indexing_service.rag_job_repository") as MockJobRepo, \
         patch("app.modules.rag.services.indexing_service.rag_job_event_repository") as MockEventRepo:
        
        MockJobRepo.get_by_id = AsyncMock(return_value=mock_job)
        MockEventRepo.get_timeline = AsyncMock(return_value=mock_timeline)
        
        service = IndexingService(adb)
        response = await service.get_job_progress(job_id)
        
        # Assertions
        assert response.job_id == job_id
        assert response.project_id == project_id
        assert response.phase == RagPhase.embed
        assert response.status == RagJobPhase.running
        assert response.progress_pct == 75  # embed phase = 75%
        assert response.event_count == 2
        
        # Verificar timeline poblada
        assert len(response.timeline) == 2
        assert response.timeline[0].phase == RagPhase.convert
        assert response.timeline[0].message == "Fase convert iniciada"
        assert response.timeline[0].progress_pct == 20
        assert response.timeline[1].phase == RagPhase.chunk
        assert response.timeline[1].progress_pct == 60
        
        MockJobRepo.get_by_id.assert_called_once_with(adb, job_id)
        MockEventRepo.get_timeline.assert_called_once_with(adb, job_id)


@pytest.mark.asyncio
async def test_get_job_progress_not_found(adb):
    """Test: Error cuando job no existe."""
    
    job_id = uuid4()
    
    with patch("app.modules.rag.services.indexing_service.rag_job_repository") as MockJobRepo:
        MockJobRepo.get_by_id = AsyncMock(return_value=None)
        
        service = IndexingService(adb)
        
        with pytest.raises(Exception) as exc_info:
            await service.get_job_progress(job_id)
        
        assert "no encontrado" in str(exc_info.value).lower() or "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_list_project_jobs_success(adb):
    """Test: Listar jobs de un proyecto."""
    
    project_id = uuid4()
    
    # Mock del proyecto
    mock_project = SimpleNamespace(
        project_id=project_id,
        project_is_archived=False,
        state=ProjectState.ready,
    )

    mock_jobs = [
        SimpleNamespace(
            job_id=uuid4(),
            project_id=project_id,
            file_id=uuid4(),
            phase_current=RagPhase.ready,  # RagPhase para pipeline phase
            status=RagJobPhase.completed,  # RagJobPhase para job status
            started_at="2025-11-28T10:00:00Z",
            completed_at="2025-11-28T10:10:00Z",
            updated_at="2025-11-28T10:10:00Z",
        ),
        SimpleNamespace(
            job_id=uuid4(),
            project_id=project_id,
            file_id=uuid4(),
            phase_current=RagPhase.chunk,  # RagPhase para pipeline phase
            status=RagJobPhase.running,  # RagJobPhase para job status
            started_at="2025-11-28T10:05:00Z",
            completed_at=None,
            updated_at="2025-11-28T10:07:00Z",
        ),
    ]
    
    with patch.object(adb, "get", AsyncMock(return_value=mock_project)), \
         patch("app.modules.rag.services.indexing_service.rag_job_repository") as MockJobRepo:
        
        MockJobRepo.list_by_project = AsyncMock(return_value=mock_jobs)
        
        service = IndexingService(adb)
        response = await service.list_project_jobs(project_id)
        
        # Assertions
        assert len(response) == 2
        assert response[0].project_id == project_id
        assert response[0].phase == RagPhase.ready  # RagPhase, not RagJobPhase
        assert response[0].progress_pct == 100
        assert response[1].phase == RagPhase.chunk  # RagPhase, not RagJobPhase
        assert response[1].progress_pct == 55  # chunk phase = 55%
        
        MockJobRepo.list_by_project.assert_called_once()


@pytest.mark.asyncio
async def test_calculate_progress_mapping():
    """Test: _calculate_progress mapea fases y estados correctamente."""
    
    from app.modules.rag.enums import RagPhase
    
    service = IndexingService(None)
    
    # Test con RagPhase (fases del pipeline)
    assert service._calculate_progress(RagPhase.convert) == 15
    assert service._calculate_progress(RagPhase.ocr) == 35
    assert service._calculate_progress(RagPhase.chunk) == 55
    assert service._calculate_progress(RagPhase.embed) == 75
    assert service._calculate_progress(RagPhase.integrate) == 90
    assert service._calculate_progress(RagPhase.ready) == 100
    
    # Test con RagJobPhase (estados del job)
    assert service._calculate_progress(RagJobPhase.queued) == 0
    assert service._calculate_progress(RagJobPhase.running) == 50
    assert service._calculate_progress(RagJobPhase.completed) == 100
    assert service._calculate_progress(RagJobPhase.failed) == 0
    assert service._calculate_progress(RagJobPhase.cancelled) == 0


# Fin del archivo backend/tests/modules/rag/services/test_indexing_service.py
