
# backend/tests/modules/payments/routes/test_webhooks_paypal_routes.py
import json
from http import HTTPStatus
import pytest


"""
Suite: Webhooks PayPal Routes
Rutas objetivo:
  - POST /payments/webhooks/paypal
Propósito:
  - Validar verificación de firma mediante verify_paypal_webhook_signature
  - Validar estructura del payload y tipos de evento soportados
  - Asegurar respuesta 2xx solo cuando el evento es válido
Requisitos:
  - La verificación de firma se realiza en services/webhooks/signature_verification.verify_paypal_webhook_signature
  - El procesamiento del evento se delega a facades/payments/webhook_handler.handle_paypal_event
  - Tests usan monkeypatch para aislar la lógica de red PayPal
"""


@pytest.fixture(autouse=True)
def _enforce_secure_webhooks(monkeypatch):
    """Fuerza verificación de firmas en todos los tests de este módulo."""
    monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
    monkeypatch.setenv("PYTHON_ENV", "test")


@pytest.mark.anyio
async def test_paypal_webhook_invalid_signature(monkeypatch, async_client):
    """Firma inválida debe devolver 401.

    Mockeamos handle_webhook en el namespace de la ruta (webhooks_paypal)
    para que lance WebhookSignatureError y verificar que responde 401.
    """
    from app.modules.payments.routes import webhooks_paypal as route_mod
    from app.modules.payments.facades.payments.webhook_handler import WebhookSignatureError
    from unittest.mock import AsyncMock

    mock_handle = AsyncMock(side_effect=WebhookSignatureError("Invalid signature"))
    monkeypatch.setattr(route_mod, "handle_webhook", mock_handle)

    payload = {"id": "WH-INV", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": "CAP-1"}}
    r = await async_client.post(
        "/payments/webhooks/paypal",
        content=json.dumps(payload),
        headers={"paypal-transmission-sig": "bad"},
    )
    assert r.status_code == HTTPStatus.UNAUTHORIZED
    assert "signature" in r.text.lower()


@pytest.mark.anyio
async def test_paypal_webhook_valid_signature(monkeypatch, async_client):
    """Firma válida debe aceptar evento y procesarlo.

    El stub verifica firma vía verify_mod.verify_paypal_signature y luego
    procesa con webhook_handler.handle_webhook. Mockeamos ambos para
    simular éxito sin depender de PayPal real.
    """
    from app.modules.payments.facades.webhooks import verify as verify_mod
    from app.modules.payments.facades.payments import webhook_handler
    from unittest.mock import AsyncMock

    # Mock de verificación de firma en el módulo verify
    monkeypatch.setattr(verify_mod, "verify_paypal_signature", AsyncMock(return_value=True))
    
    # Mock del handler para simular procesamiento exitoso
    mock_handle = AsyncMock(return_value={"status": "ok", "event": "payment_succeeded", "payment_id": 123})
    monkeypatch.setattr(webhook_handler, "handle_webhook", mock_handle)

    payload = {
        "id": "WH-VALID",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "CAP-1", "amount": {"value": "99.00", "currency_code": "MXN"}},
    }
    r = await async_client.post(
        "/payments/webhooks/paypal",
        content=json.dumps(payload),
        headers={
            "paypal-transmission-sig": "dummy",
            "paypal-transmission-id": "T-123",
            "paypal-transmission-time": "2025-01-01T00:00:00Z",
        },
    )
    assert r.status_code == HTTPStatus.OK
    mock_handle.assert_awaited_once()


@pytest.mark.anyio
async def test_paypal_webhook_missing_event_type(monkeypatch, async_client):
    """Payload sin event_type debe retornar 422 (webhook malformado)."""
    from app.modules.payments.facades.webhooks import verify as verify_mod
    from unittest.mock import AsyncMock

    # Mock verificación para pasar esa fase y llegar a validación de payload
    monkeypatch.setattr(verify_mod, "verify_paypal_signature", AsyncMock(return_value=True))

    payload = {"id": "WH-NO-TYPE", "resource": {"id": "CAP-2"}}
    r = await async_client.post(
        "/payments/webhooks/paypal",
        content=json.dumps(payload),
        headers={
            "paypal-transmission-sig": "dummy",
            "paypal-transmission-id": "T-123",
            "paypal-transmission-time": "2025-01-01T00:00:00Z",
        },
    )
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_paypal_webhook_malformed_json(async_client):
    """Payload no parseable JSON debe retornar 422."""
    r = await async_client.post("/payments/webhooks/paypal", content="not-json", headers={})
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_paypal_webhook_unknown_event_type(monkeypatch, async_client):
    """Evento desconocido debe ser ignorado y retornar 200 con status='ignored'."""
    from app.modules.payments.facades.webhooks import verify as verify_mod
    from app.modules.payments.facades.payments import webhook_handler
    from unittest.mock import AsyncMock

    # Mock verificación para pasar esa fase
    monkeypatch.setattr(verify_mod, "verify_paypal_signature", AsyncMock(return_value=True))
    mock_handle = AsyncMock(return_value={"status": "ignored", "reason": "unrecognized_event_type"})
    monkeypatch.setattr(webhook_handler, "handle_webhook", mock_handle)

    payload = {
        "id": "WH-UNKNOWN",
        "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
        "resource": {"id": "SUB-123"},
    }

    r = await async_client.post(
        "/payments/webhooks/paypal",
        content=json.dumps(payload),
        headers={
            "paypal-transmission-sig": "dummy",
            "paypal-transmission-id": "T-123",
            "paypal-transmission-time": "2025-01-01T00:00:00Z",
        },
    )

    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert data.get("status") == "ignored"
    mock_handle.assert_awaited_once()


@pytest.mark.anyio
async def test_paypal_webhook_handles_refund_completed(monkeypatch, async_client):
    """Evento REFUND.SALE.COMPLETED debe procesarse como éxito y devolver 200."""
    from app.modules.payments.facades.webhooks import verify as verify_mod
    from app.modules.payments.facades.payments import webhook_handler
    from unittest.mock import AsyncMock

    # Mock verificación para pasar esa fase
    monkeypatch.setattr(verify_mod, "verify_paypal_signature", AsyncMock(return_value=True))
    mock_handle = AsyncMock(return_value={"status": "processed", "refund_id": 456})
    monkeypatch.setattr(webhook_handler, "handle_webhook", mock_handle)

    payload = {
        "id": "WH-REFUND",
        "event_type": "REFUND.SALE.COMPLETED",
        "resource": {
            "id": "REFUND-789",
            "sale_id": "SALE-123",
            "amount": {"value": "50.00", "currency": "USD"},
        },
    }

    r = await async_client.post(
        "/payments/webhooks/paypal",
        content=json.dumps(payload),
        headers={
            "paypal-transmission-sig": "dummy",
            "paypal-transmission-id": "T-123",
            "paypal-transmission-time": "2025-01-01T00:00:00Z",
        },
    )

    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert data.get("status") == "processed"
    mock_handle.assert_awaited_once()

# Fin del archivo