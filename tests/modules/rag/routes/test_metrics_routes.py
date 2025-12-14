# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/routes/test_metrics_routes.py

Tests para rutas de métricas RAG - FASE 4.

Autor: DoxAI
Fecha: 2025-11-28 (FASE 4)
"""

import pytest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def test_client():
    """Fixture de TestClient para FastAPI."""
    return TestClient(app)


def test_metrics_prometheus_endpoint_exists(test_client):
    """Test: Endpoint /rag/metrics/prometheus existe y responde."""
    
    # Mock del servicio de métricas y prometheus client
    with patch('app.modules.rag.metrics.routes.routes_prometheus.RagMetricsService.update_prometheus_metrics', new_callable=AsyncMock) as mock_update, \
         patch('app.modules.rag.metrics.routes.routes_prometheus.generate_latest', return_value=b"# HELP rag_jobs_total Total jobs\n# TYPE rag_jobs_total counter\n"):
        
        response = test_client.get("/rag/metrics/prometheus")
        
        # Debe responder 200 con métricas
        assert response.status_code == 200


def test_metrics_snapshot_db_endpoint_exists(test_client):
    """Test: Endpoint /rag/metrics/snapshot/db existe y responde."""
    
    project_id = uuid4()
    
    # Mock del servicio de métricas
    mock_snapshot = SimpleNamespace(
        document_readiness=[],
        pipeline_latency=[],
        ocr_costs_daily=[],
        embedding_volume=[],
        embedding_coverage=[],
    )
    
    with patch('app.modules.rag.metrics.routes.routes_snapshot_db.RagMetricsService.get_db_snapshot', new_callable=AsyncMock, return_value=mock_snapshot):
        
        response = test_client.get(f"/rag/metrics/snapshot/db?project_id={project_id}&days=7")
        
        # Debe responder 200 con snapshot
        assert response.status_code == 200


def test_metrics_snapshot_memory_endpoint_exists(test_client):
    """Test: Endpoint /rag/metrics/snapshot/memory existe y responde."""
    
    from datetime import datetime
    
    # Mock del servicio de memoria con estructura correcta
    mock_snapshot = SimpleNamespace(
        running_jobs=[],  # List[RagRunningJobInfo]
        workers=[],       # List[RagWorkerHealth]
        timestamp=datetime.now(),  # datetime
    )
    
    with patch('app.modules.rag.metrics.routes.routes_snapshot_memory.RagMetricsService.get_memory_snapshot', new_callable=AsyncMock, return_value=mock_snapshot):
        
        response = test_client.get("/rag/metrics/snapshot/memory")
        
        # Debe responder 200 con snapshot
        assert response.status_code == 200


# Fin del archivo backend/tests/modules/rag/routes/test_metrics_routes.py
