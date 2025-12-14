# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/tests/test_routes.py

Tests para las rutas del módulo de proyectos.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app


client = TestClient(app)


class TestProjectRoutes:
    """Tests para endpoints de proyectos"""

    @pytest.mark.skip(reason="Requiere implementación de autenticación JWT")
    def test_create_project(self, db_session: Session, sample_user):
        """Test: crear proyecto via API"""
        payload = {
            "project_name": "API Test Project",
            "project_description": "Created via API"
        }
        
        response = client.post(
            "/projects",
            json=payload,
            headers={"Authorization": f"Bearer {sample_user.user_id}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["project"]["project_name"] == "API Test Project"

    @pytest.mark.skip(reason="Requiere implementación de autenticación JWT")
    def test_list_projects(self, db_session: Session, sample_user, sample_project):
        """Test: listar proyectos del usuario"""
        response = client.get(
            "/projects",
            headers={"Authorization": f"Bearer {sample_user.user_id}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] >= 1

    @pytest.mark.skip(reason="Requiere implementación de autenticación JWT")
    def test_get_project(self, db_session: Session, sample_user, sample_project):
        """Test: obtener proyecto específico"""
        response = client.get(
            f"/projects/{sample_project.project_id}",
            headers={"Authorization": f"Bearer {sample_user.user_id}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["project"]["project_id"] == str(sample_project.project_id)

    @pytest.mark.skip(reason="Requiere implementación de autenticación JWT")
    def test_update_project(self, db_session: Session, sample_user, sample_project):
        """Test: actualizar descripción del proyecto"""
        payload = {
            "project_description": "Updated via API"
        }
        
        response = client.put(
            f"/projects/{sample_project.project_id}",
            json=payload,
            headers={"Authorization": f"Bearer {sample_user.user_id}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["project"]["project_description"] == "Updated via API"

    @pytest.mark.skip(reason="Requiere implementación de autenticación JWT")
    def test_close_project(self, db_session: Session, sample_user, sample_project):
        """Test: cerrar proyecto"""
        response = client.post(
            f"/projects/{sample_project.project_id}/close",
            headers={"Authorization": f"Bearer {sample_user.user_id}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["project"]["project_is_closed"] is True

    @pytest.mark.skip(reason="Requiere implementación de autenticación JWT")
    def test_advance_phase(self, db_session: Session, sample_user, sample_project):
        """Test: avanzar fase del proyecto"""
        response = client.post(
            f"/projects/{sample_project.project_id}/advance-phase",
            headers={"Authorization": f"Bearer {sample_user.user_id}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.skip(reason="Requiere implementación de autenticación JWT")
    def test_get_project_activity(self, db_session: Session, sample_project, sample_activity):
        """Test: obtener historial de actividades"""
        response = client.get(
            f"/projects/{sample_project.project_id}/activity",
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] >= 1
