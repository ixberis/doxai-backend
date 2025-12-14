
# backend/tests/modules/payments/facades/webhooks/test_normalize_webhook_data.py
import json
import pytest
from starlette.requests import Request
from app.modules.payments.facades.webhooks import normalize_webhook_data, verify_and_handle_webhook
from app.modules.payments.enums import PaymentProvider

def test_normalize_webhook_data_stripe_charge_succeeded():
    payload = {
        "id": "evt_1",
        "type": "charge.succeeded",
        "data": {"object": {"id":"ch_1", "payment_intent":"pi_1"}}
    }
    n = normalize_webhook_data(PaymentProvider.STRIPE, payload)
    assert n["provider_payment_id"] == "pi_1"
    assert n["provider_event_id"] == "evt_1"
    assert n["event_type"] == "charge.succeeded"

def test_normalize_webhook_data_paypal_capture_completed():
    payload = {
        "id": "pp_evt_1",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id":"CAPTURE_ID", "supplementary_data": {"related_ids": {"order_id":"ORDER_1"}}}
    }
    n = normalize_webhook_data(PaymentProvider.PAYPAL, payload)
    assert n["provider_payment_id"] == "CAPTURE_ID"
    assert n["provider_event_id"] == "pp_evt_1"
    assert n["event_type"] == "PAYMENT.CAPTURE.COMPLETED"

@pytest.mark.asyncio
async def test_verify_and_handle_webhook_dev_insecure_ok(monkeypatch, db):
    body = json.dumps({
        "id":"evt_1",
        "type":"checkout.session.completed",
        "data":{"object":{"id":"cs_1","payment_intent":"pi_123","metadata":{"payment_id":"456"}}}
    }).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {"type":"http", "method":"POST", "headers":[(b"stripe-signature", b"t=1,v1=fakesig")]}
    req = Request(scope, receive=receive)

    async def fake_handle(db, provider, payload, provider_event_id, event_type, payment_id, provider_payment_id):
        class E: id=999
        class P: id=456
        return E(), P()

    monkeypatch.setattr(
        "app.modules.payments.facades.payments.webhook_handler.handle_webhook",
        fake_handle,
    )

    evt, pay = await verify_and_handle_webhook(
        db, req, provider=PaymentProvider.STRIPE, webhook_secret=None
    )
    assert evt.id == 999 and pay.id == 456
# Fin del archivo backend/tests/modules/payments/facades/webhooks/test_normalize_webhook_data.py
