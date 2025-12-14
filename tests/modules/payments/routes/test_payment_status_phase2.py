
# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/routes/test_payment_status_phase2.py

Tests para FASE 2: Endpoint de estado de pago para polling del Frontend.

Path final: /api/payments/{payment_id}/status (asumiendo que el router principal
monta con prefix /api).

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.modules.payments.enums import PaymentStatus
from app.modules.payments.schemas.payment_status_schemas import (
    PaymentStatusResponse,
    FINAL_STATUSES,
)


class TestFinalStatusesDefinition:
    """Tests para la definición de estados finales."""

    def test_final_statuses_are_strings(self):
        """FINAL_STATUSES debe contener strings, no enums."""
        for status in FINAL_STATUSES:
            assert isinstance(status, str), f"Expected str, got {type(status)}"

    def test_created_status_is_not_final(self):
        """Estado 'created' no es final."""
        assert "created" not in FINAL_STATUSES

    def test_pending_status_is_not_final(self):
        """Estado 'pending' no es final."""
        assert "pending" not in FINAL_STATUSES

    def test_authorized_status_is_not_final(self):
        """Estado 'authorized' no es final."""
        assert "authorized" not in FINAL_STATUSES

    def test_succeeded_status_is_final(self):
        """Estado 'succeeded' es final."""
        assert "succeeded" in FINAL_STATUSES

    def test_failed_status_is_final(self):
        """Estado 'failed' es final."""
        assert "failed" in FINAL_STATUSES

    def test_refunded_status_is_final(self):
        """Estado 'refunded' es final."""
        assert "refunded" in FINAL_STATUSES

    def test_cancelled_status_is_final(self):
        """Estado 'cancelled' es final."""
        assert "cancelled" in FINAL_STATUSES


class TestPaymentStatusResponseSchema:
    """Tests para construcción del schema de respuesta."""

    def test_response_status_is_string(self):
        """El campo status debe ser string, no enum."""
        response = PaymentStatusResponse(
            payment_id=123,
            status="pending",
            is_final=False,
            credits_awarded=0,
            webhook_verified_at=None,
            updated_at=datetime.now(timezone.utc),
            retry_after_seconds=5,
        )
        assert isinstance(response.status, str)
        assert response.status == "pending"

    def test_response_with_pending_status(self):
        """Respuesta con estado pending debe tener is_final=False."""
        response = PaymentStatusResponse(
            payment_id=123,
            status="pending",
            is_final=False,
            credits_awarded=0,
            webhook_verified_at=None,
            updated_at=datetime.now(timezone.utc),
            retry_after_seconds=5,
        )
        assert response.is_final is False
        assert response.credits_awarded == 0
        assert response.webhook_verified_at is None

    def test_response_with_succeeded_status(self):
        """Respuesta con estado succeeded debe tener is_final=True."""
        now = datetime.now(timezone.utc)
        response = PaymentStatusResponse(
            payment_id=456,
            status="succeeded",
            is_final=True,
            credits_awarded=100,
            webhook_verified_at=now,
            updated_at=now,
            retry_after_seconds=5,
        )
        assert response.is_final is True
        assert response.credits_awarded == 100
        assert response.webhook_verified_at is not None

    def test_response_with_failed_status(self):
        """Respuesta con estado failed debe tener is_final=True."""
        response = PaymentStatusResponse(
            payment_id=789,
            status="failed",
            is_final=True,
            credits_awarded=0,
            webhook_verified_at=None,
            updated_at=datetime.now(timezone.utc),
            retry_after_seconds=5,
        )
        assert response.is_final is True
        assert response.credits_awarded == 0

    def test_response_with_refunded_status(self):
        """Respuesta con estado refunded debe tener is_final=True."""
        response = PaymentStatusResponse(
            payment_id=999,
            status="refunded",
            is_final=True,
            credits_awarded=0,
            webhook_verified_at=None,
            updated_at=datetime.now(timezone.utc),
            retry_after_seconds=5,
        )
        assert response.is_final is True


class TestGetPaymentStatusFacade:
    """Tests para la facade get_payment_status."""

    @pytest.mark.asyncio
    async def test_returns_is_final_false_for_created_status(self):
        """Pago con status 'created' devuelve is_final=False."""
        from app.modules.payments.facades.payments import intents
        from app.modules.payments.repositories.payment_repository import PaymentRepository

        # Mock payment object con credits_awarded (property en modelo real)
        mock_payment = SimpleNamespace(
            id=100,
            status=PaymentStatus.CREATED,
            credits_awarded=50,  # Usar credits_awarded, no credits_purchased
            webhook_verified_at=None,
            updated_at=datetime.now(timezone.utc),
        )

        mock_repo = AsyncMock(spec=PaymentRepository)
        mock_repo.get = AsyncMock(return_value=mock_payment)
        mock_session = AsyncMock()

        result = await intents.get_payment_status(
            mock_session,
            payment_id=100,
            payment_repo=mock_repo,
        )

        assert result.payment_id == 100
        assert result.status == "created"
        assert result.is_final is False
        assert result.credits_awarded == 50

    @pytest.mark.asyncio
    async def test_returns_is_final_false_for_pending_status(self):
        """Pago con status 'pending' devuelve is_final=False."""
        from app.modules.payments.facades.payments import intents
        from app.modules.payments.repositories.payment_repository import PaymentRepository

        mock_payment = SimpleNamespace(
            id=101,
            status=PaymentStatus.PENDING,
            credits_awarded=0,
            webhook_verified_at=None,
            updated_at=datetime.now(timezone.utc),
        )

        mock_repo = AsyncMock(spec=PaymentRepository)
        mock_repo.get = AsyncMock(return_value=mock_payment)
        mock_session = AsyncMock()

        result = await intents.get_payment_status(
            mock_session,
            payment_id=101,
            payment_repo=mock_repo,
        )

        assert result.is_final is False
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_returns_is_final_true_for_succeeded_status(self):
        """Pago con status 'succeeded' devuelve is_final=True."""
        from app.modules.payments.facades.payments import intents
        from app.modules.payments.repositories.payment_repository import PaymentRepository

        now = datetime.now(timezone.utc)
        mock_payment = SimpleNamespace(
            id=102,
            status=PaymentStatus.SUCCEEDED,
            credits_awarded=100,
            webhook_verified_at=now,
            updated_at=now,
        )

        mock_repo = AsyncMock(spec=PaymentRepository)
        mock_repo.get = AsyncMock(return_value=mock_payment)
        mock_session = AsyncMock()

        result = await intents.get_payment_status(
            mock_session,
            payment_id=102,
            payment_repo=mock_repo,
        )

        assert result.is_final is True
        assert result.status == "succeeded"
        assert result.credits_awarded == 100

    @pytest.mark.asyncio
    async def test_returns_is_final_true_for_failed_status(self):
        """Pago con status 'failed' devuelve is_final=True."""
        from app.modules.payments.facades.payments import intents
        from app.modules.payments.repositories.payment_repository import PaymentRepository

        mock_payment = SimpleNamespace(
            id=103,
            status=PaymentStatus.FAILED,
            credits_awarded=0,
            webhook_verified_at=None,
            updated_at=datetime.now(timezone.utc),
        )

        mock_repo = AsyncMock(spec=PaymentRepository)
        mock_repo.get = AsyncMock(return_value=mock_payment)
        mock_session = AsyncMock()

        result = await intents.get_payment_status(
            mock_session,
            payment_id=103,
            payment_repo=mock_repo,
        )

        assert result.is_final is True
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_returns_is_final_true_for_refunded_status(self):
        """Pago con status 'refunded' devuelve is_final=True."""
        from app.modules.payments.facades.payments import intents
        from app.modules.payments.repositories.payment_repository import PaymentRepository

        mock_payment = SimpleNamespace(
            id=104,
            status=PaymentStatus.REFUNDED,
            credits_awarded=0,
            webhook_verified_at=None,
            updated_at=datetime.now(timezone.utc),
        )

        mock_repo = AsyncMock(spec=PaymentRepository)
        mock_repo.get = AsyncMock(return_value=mock_payment)
        mock_session = AsyncMock()

        result = await intents.get_payment_status(
            mock_session,
            payment_id=104,
            payment_repo=mock_repo,
        )

        assert result.is_final is True
        assert result.status == "refunded"

    @pytest.mark.asyncio
    async def test_raises_not_found_for_nonexistent_payment(self):
        """Pago inexistente lanza PaymentIntentNotFound."""
        from app.modules.payments.facades.payments import intents
        from app.modules.payments.facades.payments.intents import PaymentIntentNotFound
        from app.modules.payments.repositories.payment_repository import PaymentRepository

        mock_repo = AsyncMock(spec=PaymentRepository)
        mock_repo.get = AsyncMock(return_value=None)
        mock_session = AsyncMock()

        with pytest.raises(PaymentIntentNotFound) as exc_info:
            await intents.get_payment_status(
                mock_session,
                payment_id=999,
                payment_repo=mock_repo,
            )

        assert "999" in str(exc_info.value)


class TestPaymentStatusRoute:
    """Tests para la ruta HTTP GET /payments/{payment_id}/status."""

    @pytest.mark.asyncio
    async def test_route_returns_200_for_existing_payment(self):
        """Ruta devuelve 200 para pago existente."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.modules.payments.routes.payments import router
        from app.modules.payments.schemas.payment_status_schemas import PaymentStatusResponse

        app = FastAPI()
        app.include_router(router, prefix="/payments")

        now = datetime.now(timezone.utc)
        mock_response = PaymentStatusResponse(
            payment_id=123,
            status="pending",
            is_final=False,
            credits_awarded=0,
            webhook_verified_at=None,
            updated_at=now,
            retry_after_seconds=5,
        )

        # Patch en el módulo de rutas donde se importa get_payment_status
        with patch(
            "app.modules.payments.routes.payments.get_payment_status",
            new=AsyncMock(return_value=mock_response),
        ):
            with TestClient(app) as client:
                response = client.get("/payments/123/status")
                assert response.status_code == 200
                data = response.json()
                assert data["payment_id"] == 123
                assert data["is_final"] is False
                assert data["status"] == "pending"
                assert isinstance(data["status"], str)

    @pytest.mark.asyncio
    async def test_route_returns_404_for_nonexistent_payment(self):
        """Ruta devuelve 404 para pago inexistente."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.modules.payments.routes.payments import router
        from app.modules.payments.facades.payments.intents import PaymentIntentNotFound

        app = FastAPI()
        app.include_router(router, prefix="/payments")

        with patch(
            "app.modules.payments.routes.payments.get_payment_status",
            new=AsyncMock(side_effect=PaymentIntentNotFound("Payment 999 not found")),
        ):
            with TestClient(app) as client:
                response = client.get("/payments/999/status")
                assert response.status_code == 404
                assert "999" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_route_returns_status_as_string(self):
        """Ruta devuelve status como string, no como objeto."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.modules.payments.routes.payments import router
        from app.modules.payments.schemas.payment_status_schemas import PaymentStatusResponse

        app = FastAPI()
        app.include_router(router, prefix="/payments")

        now = datetime.now(timezone.utc)
        mock_response = PaymentStatusResponse(
            payment_id=456,
            status="succeeded",
            is_final=True,
            credits_awarded=100,
            webhook_verified_at=now,
            updated_at=now,
            retry_after_seconds=5,
        )

        with patch(
            "app.modules.payments.routes.payments.get_payment_status",
            new=AsyncMock(return_value=mock_response),
        ):
            with TestClient(app) as client:
                response = client.get("/payments/456/status")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "succeeded"
                assert isinstance(data["status"], str)
                assert data["is_final"] is True


# Fin del archivo backend/tests/modules/payments/routes/test_payment_status_phase2.py
