# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/routes/test_checkout_anti_fraud.py

Tests para validar el hardening anti-fraude del checkout:
- package_id como fuente de verdad
- Rechazo de package_id inválido
- Rechazo de payload mixto (package_id + credits/amount)
- Auth RUNTIME resolution (JWT via validate_jwt_token en prod, stub en dev)

Autor: DoxAI
Fecha: 2025-12-13
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, HTTPException, status

# Import route module for monkeypatching
import app.modules.payments.routes.checkout as checkout_route_mod
import app.modules.auth.dependencies as auth_deps_mod
from app.modules.payments.routes.checkout import router as checkout_router
from app.modules.payments.enums import PaymentProvider, Currency, PaymentStatus
from app.modules.payments.schemas import CheckoutResponse, ProviderCheckoutInfo
from app.modules.billing.credit_packages import CreditPackage


@pytest.fixture
def test_app():
    """App de prueba con solo el router de checkout."""
    app = FastAPI()
    app.include_router(checkout_router, prefix="/payments")
    return app


@pytest.fixture
def mock_db_session():
    """Mock de sesión de base de datos."""
    return AsyncMock()


@pytest.fixture
def mock_package_pro():
    """Paquete Pro para tests."""
    return CreditPackage(
        id="pkg_pro",
        name="Pro",
        credits=500,
        price_cents=39900,
        currency="MXN",
        popular=True,
    )


@pytest.fixture
def dev_mode(monkeypatch):
    """Configura entorno de desarrollo."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("PYTHON_ENV", raising=False)


@pytest.fixture
def prod_mode(monkeypatch):
    """Configura entorno de producción."""
    monkeypatch.setenv("ENVIRONMENT", "production")


@pytest.fixture
def enable_demo_user(monkeypatch, dev_mode):
    """Habilita demo-user (solo funciona en dev)."""
    monkeypatch.setenv("ALLOW_DEMO_USER", "true")


# =============================================================================
# Tests Anti-Fraude
# =============================================================================

@pytest.mark.asyncio
async def test_checkout_with_valid_package_id(
    test_app, mock_db_session, mock_package_pro, monkeypatch, enable_demo_user
):
    """
    POST /payments/checkout/start con package_id válido:
    - Debe resolver amount/credits desde el paquete
    - Retorna 201 con payment creado
    """
    monkeypatch.setattr(
        checkout_route_mod,
        "get_package_by_id",
        lambda pid: mock_package_pro if pid == "pkg_pro" else None,
    )
    
    async def fake_start_checkout(session, *, user_id, payload, payment_service):
        assert payload.credits == 500
        assert payload.amount == Decimal("399.00")
        assert payload.currency == Currency.MXN
        return CheckoutResponse(
            payment_id=123,
            provider=PaymentProvider.STRIPE,
            provider_info=ProviderCheckoutInfo(
                provider_session_id="cs_test_123",
                client_secret="pi_secret_123",
            ),
        )
    
    monkeypatch.setattr(checkout_route_mod, "start_checkout_facade", fake_start_checkout)
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 201
    data = response.json()
    assert data["payment_id"] == 123


@pytest.mark.asyncio
async def test_checkout_with_invalid_package_id(
    test_app, mock_db_session, monkeypatch, enable_demo_user
):
    """
    POST /payments/checkout/start con package_id inválido:
    - Debe retornar 400 con error "invalid_package"
    """
    monkeypatch.setattr(checkout_route_mod, "get_package_by_id", lambda pid: None)
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "package_id": "pkg_nonexistent",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "invalid_package"


@pytest.mark.asyncio
async def test_checkout_mixed_payload_rejected(
    test_app, mock_db_session, monkeypatch, enable_demo_user
):
    """
    POST /payments/checkout/start con package_id Y credits/amount:
    - Debe retornar 422 (payload mixto no permitido)
    """
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "credits": 9999,
                "amount": "0.01",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_checkout_legacy_mode_without_package_id(
    test_app, mock_db_session, monkeypatch, enable_demo_user
):
    """
    POST /payments/checkout/start sin package_id (modo legacy):
    - Requiere credits y amount explícitos
    """
    async def fake_start_checkout(session, *, user_id, payload, payment_service):
        assert payload.credits == 100
        assert payload.amount == Decimal("99.00")
        return MagicMock(
            payment_id=456,
            provider=PaymentProvider.STRIPE,
            provider_info=ProviderCheckoutInfo(provider_session_id="cs_789"),
        )
    
    monkeypatch.setattr(checkout_route_mod, "start_checkout_facade", fake_start_checkout)
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "credits": 100,
                "amount": "99.00",
                "currency": "mxn",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_checkout_missing_credits_and_amount_without_package(
    test_app, mock_db_session, monkeypatch, enable_demo_user
):
    """
    POST /payments/checkout/start sin package_id y sin credits/amount:
    - Debe retornar 422 (validation error de Pydantic)
    """
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 422


# =============================================================================
# Tests Auth - PRODUCTION MODE (validate_jwt_token via auth.dependencies)
# =============================================================================

@pytest.mark.asyncio
async def test_prod_mode_without_token_returns_401(
    test_app, mock_db_session, monkeypatch, prod_mode
):
    """
    PRODUCCIÓN sin token → 401 (authentication_required)
    """
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "authentication_required"


@pytest.mark.asyncio
async def test_prod_mode_with_invalid_token_returns_401(
    test_app, mock_db_session, monkeypatch, prod_mode
):
    """
    PRODUCCIÓN con token inválido → 401 (invalid_token)
    Mockea validate_jwt_token de auth.dependencies
    """
    # Mock validate_jwt_token para que lance 401
    def fake_validate_jwt_token(token: str) -> str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "Token inválido o expirado",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    monkeypatch.setattr(auth_deps_mod, "validate_jwt_token", fake_validate_jwt_token)
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            headers={"Authorization": "Bearer invalid_jwt_token_here"},
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_prod_mode_with_valid_jwt_returns_201(
    test_app, mock_db_session, mock_package_pro, monkeypatch, prod_mode
):
    """
    PRODUCCIÓN con JWT válido → 201
    Mockea validate_jwt_token para retornar user_id válido
    """
    # Mock validate_jwt_token para que retorne user_id
    def fake_validate_jwt_token(token: str) -> str:
        return "user_12345"
    
    monkeypatch.setattr(auth_deps_mod, "validate_jwt_token", fake_validate_jwt_token)
    
    monkeypatch.setattr(
        checkout_route_mod,
        "get_package_by_id",
        lambda pid: mock_package_pro if pid == "pkg_pro" else None,
    )
    
    async def fake_start_checkout(session, *, user_id, payload, payment_service):
        assert user_id == "user_12345"  # Del JWT mockeado
        return CheckoutResponse(
            payment_id=777,
            provider=PaymentProvider.STRIPE,
            provider_info=ProviderCheckoutInfo(provider_session_id="cs_jwt"),
        )
    
    monkeypatch.setattr(checkout_route_mod, "start_checkout_facade", fake_start_checkout)
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            headers={"Authorization": "Bearer valid_jwt_token"},
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 201
    data = response.json()
    assert data["payment_id"] == 777


@pytest.mark.asyncio
async def test_prod_mode_demo_flag_ignored(
    test_app, mock_db_session, monkeypatch, prod_mode
):
    """
    PRODUCCIÓN con ALLOW_DEMO_USER=true → aún requiere JWT (demo ignorado)
    """
    monkeypatch.setenv("ALLOW_DEMO_USER", "true")
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    # Sin token, debe fallar aunque ALLOW_DEMO_USER esté activo
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "authentication_required"


# =============================================================================
# Tests Auth - DEVELOPMENT MODE (stub)
# =============================================================================

@pytest.mark.asyncio
async def test_dev_mode_with_demo_flag_returns_201(
    test_app, mock_db_session, mock_package_pro, monkeypatch, enable_demo_user
):
    """
    DESARROLLO con ALLOW_DEMO_USER=true → 201 con demo-user (sin auth)
    """
    monkeypatch.setattr(
        checkout_route_mod,
        "get_package_by_id",
        lambda pid: mock_package_pro if pid == "pkg_pro" else None,
    )
    
    async def fake_start_checkout(session, *, user_id, payload, payment_service):
        assert user_id == "demo-user"
        return CheckoutResponse(
            payment_id=999,
            provider=PaymentProvider.STRIPE,
            provider_info=ProviderCheckoutInfo(provider_session_id="cs_demo"),
        )
    
    monkeypatch.setattr(checkout_route_mod, "start_checkout_facade", fake_start_checkout)
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_dev_mode_without_demo_flag_with_token_returns_201(
    test_app, mock_db_session, mock_package_pro, monkeypatch, dev_mode
):
    """
    DESARROLLO sin ALLOW_DEMO_USER pero con Bearer token → 201
    """
    monkeypatch.delenv("ALLOW_DEMO_USER", raising=False)
    
    monkeypatch.setattr(
        checkout_route_mod,
        "get_package_by_id",
        lambda pid: mock_package_pro if pid == "pkg_pro" else None,
    )
    
    async def fake_start_checkout(session, *, user_id, payload, payment_service):
        assert user_id.startswith("user_")
        return CheckoutResponse(
            payment_id=888,
            provider=PaymentProvider.STRIPE,
            provider_info=ProviderCheckoutInfo(provider_session_id="cs_token"),
        )
    
    monkeypatch.setattr(checkout_route_mod, "start_checkout_facade", fake_start_checkout)
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            headers={"Authorization": "Bearer valid_test_token_12345"},
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_dev_mode_without_demo_flag_without_token_returns_401(
    test_app, mock_db_session, monkeypatch, dev_mode
):
    """
    DESARROLLO sin ALLOW_DEMO_USER y sin token → 401
    """
    monkeypatch.delenv("ALLOW_DEMO_USER", raising=False)
    
    async def fake_get_session():
        yield mock_db_session
    
    from app.shared.database import database
    monkeypatch.setattr(database, "get_async_session", fake_get_session)
    
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/payments/checkout/start",
            json={
                "provider": "stripe",
                "package_id": "pkg_pro",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
        )
    
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"] == "authentication_required"


# Fin del archivo
