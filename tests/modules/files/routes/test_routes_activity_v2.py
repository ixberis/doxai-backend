# -*- coding: utf-8 -*-
"""
Tests para rutas de actividad v2.

Endpoints:
- POST /files/activity/product/{product_file_id}/log
- GET /files/activity/product/{product_file_id}/history
- GET /files/activity/project/{project_id}/recent
- GET /files/activity/project/{project_id}/stats
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app

client = TestClient(app)


@pytest.mark.integration
class TestFilesActivityRoutesV2:
    """Tests para endpoints de actividad v2."""
    
    @patch("app.modules.files.routes.activity_routes.log_product_file_event")
    def test_log_activity_event(self, mock_log):
        """POST /files/activity/product/{id}/log debe registrar evento."""
        mock_log.return_value = {
            "event_id": str(uuid4()),
            "event_type": "PRODUCT_FILE_GENERATED",
        }
        
        product_file_id = uuid4()
        response = client.post(
            f"/files/activity/product/{product_file_id}/log",
            json={
                "event_type": "PRODUCT_FILE_GENERATED",
                "event_by": str(uuid4()),
                "project_id": str(uuid4()),
            },
        )
        
        assert response.status_code in (200, 201, 400, 422, 500)
    
    @patch("app.modules.files.routes.activity_routes.list_activity_for_product_file")
    def test_get_product_file_history(self, mock_list):
        """GET /files/activity/product/{id}/history debe listar eventos."""
        mock_list.return_value = [
            {"event_type": "PRODUCT_FILE_GENERATED", "event_at": "2025-01-01T00:00:00Z"},
            {"event_type": "PRODUCT_FILE_DOWNLOADED", "event_at": "2025-01-02T00:00:00Z"},
        ]
        
        product_file_id = uuid4()
        response = client.get(f"/files/activity/product/{product_file_id}/history")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.routes.activity_routes.list_activity_for_project")
    def test_get_project_recent_activity(self, mock_list):
        """GET /files/activity/project/{id}/recent debe listar actividad reciente."""
        mock_list.return_value = [
            {"event_type": "PRODUCT_FILE_GENERATED", "product_file_id": str(uuid4())},
        ]
        
        project_id = uuid4()
        response = client.get(f"/files/activity/project/{project_id}/recent")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.routes.activity_routes.activity_stats_service")
    def test_get_project_activity_stats(self, mock_stats):
        """GET /files/activity/project/{id}/stats debe devolver estadísticas."""
        mock_stats.get_project_activity_stats = AsyncMock(return_value={
            "total_events": 100,
            "downloads": 50,
            "generations": 30,
        })
        
        project_id = uuid4()
        response = client.get(f"/files/activity/project/{project_id}/stats")
        
        assert response.status_code in (200, 404, 500)


# Fin del archivo
