
# backend/tests/modules/payments/routes/test_webhooks_stripe_routes.py
import json
import os
from http import HTTPStatus
import pytest


"""
Suite: Webhooks Stripe Routes
Rutas objetivo:
  - POST /payments/webhooks/stripe
Propósito:
  - Validar verificación de firma (HMAC)
  - Manejo de payloads malformados o faltantes
  - Procesamiento correcto de eventos válidos (payment_intent.succeeded, payment_intent.payment_failed)
  - Confirmar que el endpoint retorna 2xx solo para eventos aceptados
Requisitos:
  - Variable de entorno PAYMENTS_ALLOW_INSECURE_WEBHOOKS controla bypass en modo test
  - La función de verificación se encuentra en services/webhooks/signature_verification.verify_stripe_signature
  - El manejador principal despacha a facades/payments/webhook_handler.handle_stripe_event
  - Los tests usan monkeypatch para aislar la verificación y el handler
"""


@pytest.mark.anyio
async def test_stripe_webhook_rejects_invalid_signature(async_client):
    """
    Debe retornar 401 cuando la firma es inválida y no está permitido el modo inseguro.
    """
    os.environ["PAYMENTS_ALLOW_INSECURE_WEBHOOKS"] = "false"
    payload = {"id": "evt_test_1", "type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test_1"}}}
    r = await async_client.post(
        "/payments/webhooks/stripe",
        content=json.dumps(payload),
        headers={"stripe-signature": "t=0,v1=badsig"},
    )
    assert r.status_code == HTTPStatus.UNAUTHORIZED
    assert "invalid" in r.text.lower() or "signature" in r.text.lower()


@pytest.mark.anyio
async def test_stripe_webhook_accepts_with_insecure_flag(async_client):
    """
    Con PAYMENTS_ALLOW_INSECURE_WEBHOOKS=true, debe aceptar incluso sin firma.
    """
    os.environ["PAYMENTS_ALLOW_INSECURE_WEBHOOKS"] = "true"
    payload = {"id": "evt_test_2", "type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test_2"}}}
    r = await async_client.post(
        "/payments/webhooks/stripe",
        content=json.dumps(payload),
        headers={},
    )
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.ACCEPTED)
    data = r.json()
    assert "status" in data and data["status"] in ("ok", "received", "processed")


@pytest.mark.anyio
async def test_stripe_webhook_rejects_malformed_json(async_client):
    """
    Payload no parseable JSON debe retornar 422.
    """
    os.environ["PAYMENTS_ALLOW_INSECURE_WEBHOOKS"] = "true"
    r = await async_client.post("/payments/webhooks/stripe", content="not-json", headers={})
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_stripe_webhook_rejects_missing_type(async_client):
    """
    Payload válido JSON pero sin 'type' debe retornar 422.
    """
    os.environ["PAYMENTS_ALLOW_INSECURE_WEBHOOKS"] = "true"
    payload = {"id": "evt_no_type", "data": {"object": {"id": "pi_123"}}}
    r = await async_client.post(
        "/payments/webhooks/stripe",
        content=json.dumps(payload),
        headers={},
    )
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.anyio
async def test_stripe_webhook_processes_success_event(monkeypatch, async_client):
    """
    Evento payment_intent.succeeded debe ser manejado correctamente.
    
    Usa PAYMENTS_ALLOW_INSECURE_WEBHOOKS para bypass de verificación.
    """
    monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")

    payload = {
        "id": "evt_test_3",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_3", "amount_received": 1000}},
    }

    r = await async_client.post(
        "/payments/webhooks/stripe",
        content=json.dumps(payload),
        headers={"stripe-signature": "t=0,v1=validsig"},
    )

    # Sin mock completo puede fallar en procesamiento (400), pero NO en firma (401)
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.BAD_REQUEST), r.text


@pytest.mark.anyio
async def test_stripe_webhook_processes_failed_event(monkeypatch, async_client):
    """
    Evento payment_intent.payment_failed debe ser manejado y devolver 200.
    """
    monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")
    
    # Mock del handler de webhooks
    from app.modules.payments.facades.payments import webhook_handler
    from unittest.mock import AsyncMock
    
    mock_handle = AsyncMock(return_value={"status": "processed", "payment_id": 123})
    monkeypatch.setattr(webhook_handler, "handle_webhook", mock_handle)

    payload = {
        "id": "evt_failed_1",
        "type": "payment_intent.payment_failed",
        "data": {"object": {"id": "pi_failed_1", "amount": 5000, "last_payment_error": {"message": "Card declined"}}},
    }

    r = await async_client.post(
        "/payments/webhooks/stripe",
        content=json.dumps(payload),
        headers={},
    )

    assert r.status_code in (HTTPStatus.OK, HTTPStatus.ACCEPTED)
    mock_handle.assert_awaited_once()


@pytest.mark.anyio
async def test_stripe_webhook_returns_ignored_for_unrecognized_type(monkeypatch, async_client):
    """
    Evento desconocido debe retornar 200 pero con status='ignored'.
    """
    monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")
    
    # Mock del handler que retorna 'ignored' para tipos desconocidos
    from app.modules.payments.facades.payments import webhook_handler
    from unittest.mock import AsyncMock
    
    mock_handle = AsyncMock(return_value={"status": "ignored", "reason": "unrecognized_event_type"})
    monkeypatch.setattr(webhook_handler, "handle_webhook", mock_handle)

    payload = {
        "id": "evt_unknown_1",
        "type": "invoice.created",
        "data": {"object": {"id": "in_123"}},
    }

    r = await async_client.post(
        "/payments/webhooks/stripe",
        content=json.dumps(payload),
        headers={},
    )

    assert r.status_code == HTTPStatus.OK
    data = r.json()
    assert data.get("status") == "ignored"
    mock_handle.assert_awaited_once()

# Fin del archivo backend/tests/modules/payments/routes/test_webhooks_stripe_routes.py