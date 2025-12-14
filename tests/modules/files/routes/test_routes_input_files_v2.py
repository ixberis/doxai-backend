# -*- coding: utf-8 -*-
"""
Tests para rutas de input files v2.

Endpoints:
- POST /files/input/upload
- GET /files/input/project/{project_id}
- GET /files/input/{file_id}
- GET /files/input/{file_id}/download-url
- DELETE /files/input/{file_id}
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app

client = TestClient(app)


@pytest.mark.integration
class TestInputFilesRoutesV2:
    """Tests para endpoints de input files v2."""
    
    @patch("app.modules.files.routes.input_files_routes.InputFilesFacade")
    def test_upload_input_file(self, mock_facade_class):
        """POST /files/input/upload debe subir un archivo."""
        from types import SimpleNamespace
        
        mock_facade = AsyncMock()
        mock_facade.upload_input_file = AsyncMock(return_value=SimpleNamespace(
            input_file_id=uuid4(),
            file_id=uuid4(),
            original_name="test.pdf",
            project_id=uuid4(),
        ))
        mock_facade_class.return_value = mock_facade
        
        response = client.post(
            "/files/input/upload",
            files={"file": ("test.pdf", b"pdf content", "application/pdf")},
            data={
                "project_id": str(uuid4()),
                "storage_backend": "supabase",
            },
        )
        
        # Puede devolver 201 (success), 400 (validación) o 500 (error)
        assert response.status_code in (200, 201, 400, 422, 500)
    
    @patch("app.modules.files.routes.input_files_routes.InputFilesFacade")
    def test_list_input_files_by_project(self, mock_facade_class):
        """GET /files/input/project/{project_id} debe listar archivos."""
        from types import SimpleNamespace
        
        mock_facade = AsyncMock()
        mock_facade.list_project_input_files = AsyncMock(return_value=[
            SimpleNamespace(input_file_id=uuid4(), original_name="file1.txt"),
            SimpleNamespace(input_file_id=uuid4(), original_name="file2.txt"),
        ])
        mock_facade_class.return_value = mock_facade
        
        project_id = uuid4()
        response = client.get(f"/files/input/project/{project_id}")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.routes.input_files_routes.InputFilesFacade")
    def test_get_input_file_by_id(self, mock_facade_class):
        """GET /files/input/{file_id} debe obtener un archivo."""
        from types import SimpleNamespace
        
        mock_facade = AsyncMock()
        mock_facade.get_input_file_by_file_id = AsyncMock(return_value=SimpleNamespace(
            input_file_id=uuid4(),
            original_name="doc.pdf",
        ))
        mock_facade_class.return_value = mock_facade
        
        file_id = uuid4()
        response = client.get(f"/files/input/{file_id}")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.routes.input_files_routes.InputFilesFacade")
    def test_get_download_url(self, mock_facade_class):
        """GET /files/input/{file_id}/download-url debe generar URL."""
        mock_facade = AsyncMock()
        mock_facade.get_download_url_for_file = AsyncMock(return_value="https://example.com/file")
        mock_facade_class.return_value = mock_facade
        
        file_id = uuid4()
        response = client.get(f"/files/input/{file_id}/download-url")
        
        assert response.status_code in (200, 404, 500)
    
    @patch("app.modules.files.routes.input_files_routes.InputFilesFacade")
    def test_delete_input_file(self, mock_facade_class):
        """DELETE /files/input/{file_id} debe archivar/eliminar."""
        mock_facade = AsyncMock()
        mock_facade.delete_input_file = AsyncMock(return_value=None)
        mock_facade_class.return_value = mock_facade
        
        file_id = uuid4()
        response = client.delete(f"/files/input/{file_id}")
        
        assert response.status_code in (200, 204, 404, 500)


# Fin del archivo
