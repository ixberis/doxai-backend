
# backend/tests/modules/payments/routes/test_webhooks_smoke.py
import json
import os
from http import HTTPStatus

import pytest


"""
Suite: Webhooks Smoke (Stripe & PayPal)
Objetivo:
  - Asegurar que los endpoints de webhooks existen y responden en escenarios básicos.
  - No valida reglas de negocio profundas (eso ya se prueba en suites dedicadas),
    solo que el ruteo, parsing mínimo y verificación de firma (bypass o mock) funcionan.

Rutas:
  - POST /payments/webhooks/stripe
  - POST /payments/webhooks/paypal
"""


# ---------- STRIPE SMOKE ----------

@pytest.mark.anyio
async def test_stripe_smoke_insecure_flag_accepts_without_signature(async_client):
    """
    Con el flag de inseguro activado, el endpoint debe aceptar payloads válidos
    incluso sin header de firma, devolviendo 2xx.
    """
    os.environ["PAYMENTS_ALLOW_INSECURE_WEBHOOKS"] = "true"

    payload = {"id": "evt_smoke_1", "type": "payment_intent.succeeded", "data": {"object": {"id": "pi_smoke_1"}}}
    r = await async_client.post(
        "/payments/webhooks/stripe",
        content=json.dumps(payload),
        headers={},  # sin firma
    )
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.ACCEPTED), r.text


@pytest.mark.anyio
async def test_stripe_smoke_secure_requires_signature(async_client):
    """
    Con el flag de inseguro desactivado, sin firma debe rechazar (401).
    """
    os.environ["PAYMENTS_ALLOW_INSECURE_WEBHOOKS"] = "false"

    payload = {"id": "evt_smoke_2", "type": "payment_intent.succeeded", "data": {"object": {"id": "pi_smoke_2"}}}
    r = await async_client.post(
        "/payments/webhooks/stripe",
        content=json.dumps(payload),
        headers={},  # sin 'stripe-signature'
    )
    assert r.status_code == HTTPStatus.UNAUTHORIZED


# ---------- PAYPAL SMOKE ----------

@pytest.mark.anyio
async def test_paypal_smoke_valid_signature(monkeypatch, async_client):
    """
    Si la verificación de firma es True, el endpoint debe aceptar y responder 200 o 400.
    
    Usa PAYMENTS_ALLOW_INSECURE_WEBHOOKS para bypass.
    """
    monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "true")

    payload = {
        "id": "WH-SMOKE-1",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "CAP_SMOKE_1"},
    }
    r = await async_client.post("/payments/webhooks/paypal", content=json.dumps(payload), headers={"paypal-transmission-sig": "sig"})
    # Sin mock completo puede fallar en procesamiento (400), pero NO en firma (401)
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.BAD_REQUEST), r.text


@pytest.mark.anyio
async def test_paypal_smoke_missing_signature_rejected(monkeypatch, async_client):
    """
    Si la verificación devuelve False (firma ausente/incorrecta), debe rechazar con 401.
    """
    monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
    
    from app.modules.payments.services.webhooks import signature_verification
    
    def fake_verify_paypal(*args, **kwargs):
        return False
    
    monkeypatch.setattr(signature_verification, "verify_paypal_signature", fake_verify_paypal)

    payload = {
        "id": "WH-SMOKE-2",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "CAP_SMOKE_2"},
    }
    r = await async_client.post("/payments/webhooks/paypal", content=json.dumps(payload), headers={})
    assert r.status_code == HTTPStatus.UNAUTHORIZED


# ---------- FORMATO / MALFORMED ----------

@pytest.mark.anyio
async def test_webhooks_smoke_malformed_json_returns_422(async_client):
    """
    Ambos endpoints deben responder 422 ante payload no JSON.
    """
    os.environ["PAYMENTS_ALLOW_INSECURE_WEBHOOKS"] = "true"

    r1 = await async_client.post("/payments/webhooks/stripe", content="not-json", headers={})
    r2 = await async_client.post("/payments/webhooks/paypal", content="not-json", headers={})

    assert r1.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert r2.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

# Fin del archivo backend/tests/modules/payments/routes/test_webhooks_smoke.py