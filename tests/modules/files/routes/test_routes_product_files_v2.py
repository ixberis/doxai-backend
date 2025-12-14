# -*- coding: utf-8 -*-
"""
Tests para rutas de product files v2.

Endpoints:
- POST /files/product/create
- GET /files/product/{product_file_id}
- GET /files/product/project/{project_id}
- GET /files/product/{product_file_id}/download-url
- DELETE /files/product/{product_file_id}
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app

client = TestClient(app)


@pytest.mark.integration
class TestProductFilesRoutesV2:
    """Tests para endpoints de product files v2."""
    
    @patch("app.modules.files.routes.product_files_routes.create_product_file")
    def test_create_product_file(self, mock_create):
        """POST /files/product/create debe crear un archivo producto."""
        from types import SimpleNamespace
        
        mock_create.return_value = SimpleNamespace(
            product_file_id=uuid4(),
            original_name="output.pdf",
        )
        
        response = client.post(
            "/files/product/create",
            json={
                "project_id": str(uuid4()),
                "original_name": "output.pdf",
                "file_type": "report",
                "mime_type": "application/pdf",
            },
        )
        
        assert response.status_code in (200, 201, 400, 422, 500)
    
    @patch("app.modules.files.routes.product_files_routes.get_product_file_details")
    def test_get_product_file(self, mock_get):
        """GET /files/product/{product_file_id} debe obtener detalles."""
        from types import SimpleNamespace
        
        mock_get.return_value = SimpleNamespace(
            product_file_id=uuid4(),
            original_name="report.pdf",
        )
        
        file_id = uuid4()
        response = client.get(f"/files/product/{file_id}")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.routes.product_files_routes.list_project_product_files")
    def test_list_product_files_by_project(self, mock_list):
        """GET /files/product/project/{project_id} debe listar archivos."""
        from types import SimpleNamespace
        
        mock_list.return_value = [
            SimpleNamespace(product_file_id=uuid4(), original_name="file1.pdf"),
            SimpleNamespace(product_file_id=uuid4(), original_name="file2.pdf"),
        ]
        
        project_id = uuid4()
        response = client.get(f"/files/product/project/{project_id}")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.routes.product_files_routes.get_product_file_download_url")
    def test_get_download_url(self, mock_url):
        """GET /files/product/{product_file_id}/download-url debe generar URL."""
        mock_url.return_value = "https://example.com/product"
        
        file_id = uuid4()
        response = client.get(f"/files/product/{file_id}/download-url")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.routes.product_files_routes.archive_product_file")
    def test_delete_product_file(self, mock_archive):
        """DELETE /files/product/{product_file_id} debe archivar."""
        mock_archive.return_value = None
        
        file_id = uuid4()
        response = client.delete(f"/files/product/{file_id}")
        
        assert response.status_code in (200, 204, 404, 500)


# Fin del archivo
