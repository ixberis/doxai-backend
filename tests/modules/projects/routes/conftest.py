# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/routes/conftest.py

Configuración de tests para las rutas del módulo Projects v2.
Usa servicios in-memory para tests de integración.

Autor: Ixchel Beristain
Fecha: 2025-11-08 (actualizado 2025-11-21 para Projects v2)
"""
import pytest
from uuid import UUID
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.modules.projects.routes import get_projects_router
from app.modules.projects.routes import deps as projects_deps
from app.modules.projects.services.inmemory import (
    InMemoryProjectsCommandService,
    InMemoryProjectsQueryService,
)
from app.modules.auth import services as auth_module


@pytest.fixture
def test_user_id():
    """ID de usuario fijo para tests."""
    return UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def test_user_email():
    """Email de usuario fijo para tests."""
    return "test@example.com"


@pytest.fixture
def client(test_user_id, test_user_email):
    """
    TestClient para probar endpoints del módulo Projects v2.
    Usa servicios in-memory y overridea dependencias.
    """
    # Crear app de test
    app = FastAPI(title="Projects Test App")
    app.include_router(get_projects_router())
    
    # Usuario fijo para tests
    async def _override_get_current_user():
        return {
            "user_id": str(test_user_id),
            "email": test_user_email
        }
    
    # Servicios in-memory para tests
    def _override_command_service():
        return InMemoryProjectsCommandService()
    
    def _override_query_service():
        return InMemoryProjectsQueryService(default_user_id=test_user_id)
    
    # Override de dependencias
    app.dependency_overrides[auth_module.get_current_user] = _override_get_current_user
    app.dependency_overrides[projects_deps.get_projects_command_service] = _override_command_service
    app.dependency_overrides[projects_deps.get_projects_query_service] = _override_query_service
    
    client_instance = TestClient(app)
    yield client_instance
    
    # Limpiar overrides después del test
    app.dependency_overrides.clear()
