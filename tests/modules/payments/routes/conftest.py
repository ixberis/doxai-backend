
# backend/tests/modules/payments/routes/conftest.py
# -*- coding: utf-8 -*-
"""
Conftest específico para pruebas de ruteadores del módulo Payments.

Cambios clave:
- Activa USE_PAYMENT_STUBS y banderas locales *antes* de importar la app,
  para que app.routes monte el router de stubs (checkout/webhooks) y evitemos 404.
- Usa httpx>=0.28 con ASGITransport y asgi-lifespan para manejar el ciclo de vida.
"""

from __future__ import annotations

import os
import pytest
from datetime import datetime, timedelta, timezone
from collections.abc import AsyncIterator

# === FLAGS CRÍTICOS (deben estar antes de importar la app) ===
os.environ.setdefault("USE_PAYMENT_STUBS", "true")
os.environ.setdefault("PAYMENTS_ALLOW_HTTP_LOCAL", "true")
os.environ.setdefault("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")

from httpx import AsyncClient, ASGITransport
from asgi_lifespan import LifespanManager

# ------------------------------------------------------------
# FIXTURE PRINCIPAL: APP
# ------------------------------------------------------------
@pytest.fixture(scope="session")
def app():
    """Obtiene la aplicación FastAPI principal para los tests (con stubs activos)."""
    # Import después de setear las env vars para asegurar el montaje de stubs
    from app.main import app as fastapi_app
    return fastapi_app

# ------------------------------------------------------------
# CLIENTE HTTP ASÍNCRONO
# ------------------------------------------------------------
@pytest.fixture
async def async_client(app) -> AsyncIterator[AsyncClient]:
    """
    Cliente HTTP asíncrono configurado con la app FastAPI.
    Usa ASGITransport (httpx>=0.28) y asgi-lifespan para startup/shutdown.
    """
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

# ------------------------------------------------------------
# AUTENTICACIÓN Y HEADERS
# ------------------------------------------------------------
@pytest.fixture
def auth_headers():
    """Genera encabezados de autenticación simulados."""
    def _make_headers(user_id: int = 1) -> dict[str, str]:
        return {
            "Authorization": f"Bearer fake-token-for-user-{user_id}",
            "X-User-ID": str(user_id),
        }
    return _make_headers

# ------------------------------------------------------------
# LIMPIEZA DE ESTADO ENTRE TESTS
# ------------------------------------------------------------
@pytest.fixture(autouse=True)
def reset_payment_stubs():
    """
    Limpia el estado de los stubs de pagos antes de cada test.
    Esto garantiza que cada test empiece con un estado limpio.
    """
    from app.modules.payments.routes._stubs_tests_routes import (
        _seed_test_payments,
        _RESERVATIONS,
        _RESERVATION_IDEM,
        _WALLETS,
    )
    
    # Restaurar pagos y limpiar refunds
    _seed_test_payments(clear_refunds=True)
    
    # Limpiar reservaciones
    _RESERVATIONS.clear()
    _RESERVATION_IDEM.clear()
    
    # Restaurar wallets a estado inicial
    _WALLETS.clear()
    _WALLETS.update({
        1: {"user_id": 1, "balance": 2000, "balance_available": 1800, "balance_reserved": 200},
        2: {"user_id": 2, "balance": 10, "balance_available": 10, "balance_reserved": 0},
    })
    
    # Pre-poblar reservaciones seedeadas para fixtures
    _RESERVATIONS[100] = {
        "reservation_id": 100,
        "user_id": 1,
        "credits": 10,
        "status": "created",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "consumed_at": None,
        "released_at": None,
    }
    
    _RESERVATIONS[101] = {
        "reservation_id": 101,
        "user_id": 1,
        "credits": 5,
        "status": "consumed",
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "consumed_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "released_at": None,
    }
    
    _RESERVATIONS[102] = {
        "reservation_id": 102,
        "user_id": 1,
        "credits": 8,
        "status": "expired",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        "consumed_at": None,
        "released_at": None,
    }
    
    yield
    
    # Opcionalmente limpiar después del test también
    _seed_test_payments(clear_refunds=True)
    _RESERVATIONS.clear()
    _RESERVATION_IDEM.clear()

# ------------------------------------------------------------
# FIXTURES DE PAGOS
# ------------------------------------------------------------
@pytest.fixture
def seeded_paid_payment():
    return {
        "payment_id": 10,
        "user_id": 1,
        "amount_cents": 9900,
        "currency": "mxn",
        "credits_purchased": 600,
        "status": "paid",
        "provider": "stripe",
        "provider_payment_id": "pi_test_10",
        "created_at": datetime.now(timezone.utc) - timedelta(hours=1),
    }

@pytest.fixture
def seeded_refunded_payment():
    return {
        "payment_id": 11,
        "user_id": 1,
        "amount_cents": 9900,
        "currency": "mxn",
        "credits_purchased": 600,
        "status": "refunded",
        "provider": "paypal",
        "provider_payment_id": "pi_test_11",
        "created_at": datetime.now(timezone.utc) - timedelta(days=1),
    }

@pytest.fixture
def seeded_pending_payment():
    return {
        "payment_id": 12,
        "user_id": 1,
        "amount_cents": 5000,
        "currency": "mxn",
        "credits_purchased": 300,
        "status": "pending",
        "provider": "stripe",
        "provider_payment_id": "pi_test_12",
        "created_at": datetime.now(timezone.utc),
    }

# ------------------------------------------------------------
# FIXTURES DE WALLET
# ------------------------------------------------------------
@pytest.fixture
def user_with_wallet():
    return {"user_id": 1, "balance": 2000, "balance_available": 1800, "balance_reserved": 200, "currency": "mxn"}

@pytest.fixture
def low_balance_wallet():
    return {"user_id": 2, "balance": 10, "balance_available": 10, "balance_reserved": 0, "currency": "mxn"}

# ------------------------------------------------------------
# FIXTURES DE RESERVAS
# ------------------------------------------------------------
@pytest.fixture
def seeded_reservation():
    return {
        "reservation_id": 100,
        "user_id": 1,
        "credits": 10,
        "status": "created",
        "created_at": datetime.now(timezone.utc),
    }

@pytest.fixture
def consumed_reservation():
    return {
        "reservation_id": 101,
        "user_id": 1,
        "credits": 5,
        "status": "consumed",
        "created_at": datetime.now(timezone.utc) - timedelta(hours=2),
    }

@pytest.fixture
def expired_reservation():
    return {
        "reservation_id": 102,
        "user_id": 1,
        "credits": 8,
        "status": "expired",
        "created_at": datetime.now(timezone.utc) - timedelta(days=3),
    }

# Fin del archivo backend/tests/modules/payments/routes/conftest.py
