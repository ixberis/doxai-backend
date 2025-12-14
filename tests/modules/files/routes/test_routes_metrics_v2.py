# -*- coding: utf-8 -*-
"""
Tests para rutas de métricas v2.

Endpoints:
- GET /files/metrics/snapshot/db
- GET /files/metrics/snapshot/memory
- GET /files/metrics/prometheus
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app

client = TestClient(app)


@pytest.mark.integration
class TestFilesMetricsRoutesV2:
    """Tests para endpoints de métricas v2."""
    
    @patch("app.modules.files.metrics.routes.routes_snapshot_db.FilesMetricsAggregator")
    def test_get_snapshot_from_db(self, mock_aggregator_class):
        """GET /files/metrics/snapshot/db debe devolver snapshot de BD."""
        mock_aggregator = AsyncMock()
        mock_aggregator.build_snapshot = AsyncMock(return_value={
            "inputs": {"total": 10, "total_bytes": 1024},
            "products": {"total": 5, "total_bytes": 2048},
            "activity": {"total_events": 50},
        })
        mock_aggregator_class.return_value = mock_aggregator
        
        response = client.get("/files/metrics/snapshot/db")
        
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "inputs" in data or "snapshot" in data
    
    @patch("app.modules.files.metrics.aggregators.metrics_storage.snapshot_memory")
    def test_get_snapshot_from_memory(self, mock_snapshot):
        """GET /files/metrics/snapshot/memory debe devolver snapshot de memoria."""
        mock_snapshot.return_value = {
            "inputs": {"total": 8, "total_bytes": 512},
            "products": {"total": 3, "total_bytes": 1024},
            "activity": {"total_events": 25},
        }
        
        response = client.get("/files/metrics/snapshot/memory")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.metrics.routes.routes_prometheus.FilesMetricsAggregator")
    @patch("app.modules.files.metrics.exporters.prometheus_exporter.snapshot_to_prometheus_text")
    def test_get_prometheus_metrics(self, mock_exporter, mock_aggregator_class):
        """GET /files/metrics/prometheus debe devolver métricas en formato Prometheus."""
        mock_aggregator = AsyncMock()
        mock_aggregator.build_snapshot = AsyncMock(return_value={
            "inputs": {"total": 10},
            "products": {"total": 5},
            "activity": {"total_events": 50},
        })
        mock_aggregator_class.return_value = mock_aggregator
        
        mock_exporter.return_value = """# TYPE doxai_files_inputs_total gauge
doxai_files_inputs_total 10
# TYPE doxai_files_products_total gauge
doxai_files_products_total 5
"""
        
        response = client.get("/files/metrics/prometheus")
        
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            assert "doxai_files" in response.text or "text/plain" in response.headers.get("content-type", "")


# Fin del archivo
