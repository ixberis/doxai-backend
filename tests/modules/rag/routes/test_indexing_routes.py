# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/routes/test_indexing_routes.py

Tests de integración para rutas HTTP de indexación RAG.

Autor: Ixchel Beristain
Fecha: 2025-11-28 (FASE 3)
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def test_client():
    """Fixture de TestClient para FastAPI."""
    return TestClient(app)


def test_create_indexing_job_endpoint(test_client: TestClient):
    """Test: POST /rag/projects/{project_id}/jobs/indexing crea job correctamente."""
    
    project_id = uuid4()
    file_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    
    payload = {
        "project_id": str(project_id),
        "file_id": str(file_id),
        "user_id": str(user_id),
        "mime_type": "application/pdf",
        "needs_ocr": False,
    }
    
    # Mock storage client y facades
    mock_storage = AsyncMock()
    mock_summary = SimpleNamespace(
        job_id=job_id,
        phases_done=[],
        job_status="completed",
        total_chunks=5,
        total_embeddings=5,
        credits_used=20,
        reservation_id=1,
    )
    
    # Mock job creado
    mock_job = SimpleNamespace(
        job_id=job_id,
        project_id=project_id,
        file_id=file_id,
        created_by=user_id,
        status="completed",
        phase_current="ready",
        created_at="2025-11-28T10:00:00Z",
        updated_at="2025-11-28T10:10:00Z",
    )
    
    with patch('app.modules.rag.routes.indexing.routes_indexing_jobs.get_storage_client', return_value=mock_storage), \
         patch('app.modules.rag.routes.indexing.routes_indexing_jobs.run_indexing_job', return_value=mock_summary), \
         patch('app.modules.rag.routes.indexing.routes_indexing_jobs.RagJobRepository') as MockRepo:
        
        mock_repo = MockRepo.return_value
        mock_repo.get_by_id = AsyncMock(return_value=mock_job)
        
        response = test_client.post(
            f"/rag/projects/{project_id}/jobs/indexing",
            json=payload,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert data["project_id"] == str(project_id)


def test_get_job_progress_endpoint(test_client: TestClient):
    """Test: GET /rag/jobs/{job_id}/progress retorna estado del job."""
    
    job_id = uuid4()
    
    # Mock job repository
    mock_job = SimpleNamespace(
        job_id=job_id,
        project_id=uuid4(),
        file_id=uuid4(),
        status="running",
        phase_current="chunk",
        created_at="2025-11-28T10:00:00Z",
        updated_at="2025-11-28T10:05:00Z",
        completed_at=None,
        failed_at=None,
        cancelled_at=None,
    )
    
    with patch('app.modules.rag.routes.indexing.routes_indexing_jobs.RagJobRepository') as MockRepo:
        mock_repo = MockRepo.return_value
        mock_repo.get_by_id = AsyncMock(return_value=mock_job)
        
        with patch('app.modules.rag.routes.indexing.routes_indexing_jobs.RagJobEventRepository') as MockEventRepo:
            mock_event_repo = MockEventRepo.return_value
            mock_event_repo.get_timeline = AsyncMock(return_value=[])
            
            response = test_client.get(f"/rag/jobs/{job_id}/progress")
            
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == str(job_id)
            assert "phase" in data
            assert "progress_pct" in data


def test_list_project_jobs_endpoint(test_client: TestClient):
    """Test: GET /rag/projects/{project_id}/jobs retorna lista de jobs."""
    
    project_id = uuid4()
    
    # Mock job repository
    mock_jobs = [
        SimpleNamespace(
            job_id=uuid4(),
            project_id=project_id,
            file_id=uuid4(),
            status="completed",
            phase_current="ready",
            created_at="2025-11-28T10:00:00Z",
            updated_at="2025-11-28T10:10:00Z",
            completed_at="2025-11-28T10:10:00Z",
            failed_at=None,
            cancelled_at=None,
        ),
    ]
    
    with patch('app.modules.rag.routes.indexing.routes_indexing_jobs.RagJobRepository') as MockRepo:
        mock_repo = MockRepo.return_value
        mock_repo.list_by_project = AsyncMock(return_value=mock_jobs)
        
        response = test_client.get(f"/rag/projects/{project_id}/jobs")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0


# Fin del archivo backend/tests/modules/rag/routes/test_indexing_routes.py
