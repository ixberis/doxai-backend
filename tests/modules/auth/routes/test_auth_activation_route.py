
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/routes/test_auth_activation_route.py

Test de integración ligero para la ruta /auth/activation:

- Verifica que el contrato JSON incluye el campo credits_assigned.
- Verifica que la ruta propaga correctamente el resultado de AuthFacade.activate_account.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.auth.routes import get_auth_routers
from app.modules.auth.facades import get_auth_facade


@pytest.fixture
def app_test() -> FastAPI:
    """Aplicación de prueba con routers de Auth."""
    app = FastAPI()
    for router in get_auth_routers():
        app.include_router(router)
    return app


@pytest.fixture
def client(app_test: FastAPI) -> TestClient:
    """Cliente de prueba síncrono para la API."""
    return TestClient(app_test)


def test_auth_activation_route_includes_credits_assigned(
    app_test: FastAPI, 
    client: TestClient
) -> None:
    """
    La ruta /auth/activation debe:
    - llamar a AuthFacade.activate_account(payload)
    - exponer el campo credits_assigned en la respuesta JSON.
    """
    # Mock del facade con respuesta de activación exitosa
    mock_facade = MagicMock()
    mock_facade.activate_account = AsyncMock(
        return_value={
            "message": "La cuenta se activó exitosamente.",
            "code": "ACCOUNT_ACTIVATED",
            "credits_assigned": 5,
        }
    )

    # Override de dependencia (patrón usado en test_routes.py)
    app_test.dependency_overrides[get_auth_facade] = lambda: mock_facade

    try:
        # LLamada HTTP real vía TestClient
        response = client.post("/auth/activation", json={"token": "dummy-token"})

        assert response.status_code == 200
        data = response.json()

        # El contrato debe incluir credits_assigned y el código correcto
        assert data["code"] == "ACCOUNT_ACTIVATED"
        assert data["credits_assigned"] == 5
        assert "activó exitosamente" in data["message"]

        # Verificamos que el facade fue invocado
        mock_facade.activate_account.assert_awaited_once()
    finally:
        # Limpiar override
        app_test.dependency_overrides.pop(get_auth_facade, None)


# Fin del script backend/tests/modules/auth/routes/test_auth_activation_route.py
