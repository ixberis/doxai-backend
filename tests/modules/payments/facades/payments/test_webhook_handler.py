# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/facades/payments/test_webhook_handler.py

Tests para el handler unificado de webhooks.

Autor: DoxAI
Fecha: 2025-12-13
"""
import pytest
import json
from unittest.mock import AsyncMock

from app.modules.payments.facades.payments import handle_webhook
from app.modules.payments.enums import PaymentProvider, PaymentStatus


@pytest.mark.asyncio
async def test_handle_webhook_resolves_payment_and_credits(monkeypatch, db, make_payment):
    class FakePaymentService:
        def __init__(self, session): 
            self.session = session
        async def apply_success(self, payment_id):
            return make_payment(id=payment_id, status=PaymentStatus.PAID)

    class FakePaymentRepo:
        async def get_by_id(self, session, payment_id):
            return make_payment(id=payment_id, status=type("S", (), {"value": "pending"})())

    class FakeRefundService:
        def __init__(self, session): 
            self.session = session

    class FakeRefundRepo:
        pass

    class FakeEventSvc:
        def __init__(self, repo): 
            self.repo = repo
        async def register_event(self, session, payment_id, provider_event_id, event_type, payload):
            event = type("Event", (), {"id": 999, "processed": False, "event_payload": payload})()
            return event

    # Mockear verificación de firma (debe ser async porque verify_webhook_signature es async)
    async def fake_verify(provider, raw_body, headers):
        return True
    
    monkeypatch.setattr(
        "app.modules.payments.facades.payments.webhook_handler.verify_webhook_signature",
        fake_verify,
    )

    # Mockear normalización de webhook
    class FakeNormalized:
        def __init__(self):
            self.payment_id = 222
            self.event_id = "evt_1"
            self.event_type = "checkout.session.completed"
            self.raw = {"type": "checkout.session.completed"}
            self.is_success = True
            self.is_failure = False
            self.is_refund = False
            self.failure_reason = None
            self.provider_payment_id = None

    monkeypatch.setattr(
        "app.modules.payments.facades.payments.webhook_handler.normalize_webhook_payload",
        lambda provider, raw_body, headers: FakeNormalized(),
    )

    # Mockear handle_payment_success
    fake_payment = make_payment(id=222, status=PaymentStatus.SUCCEEDED)
    async def fake_handle_payment_success(**kwargs):
        return fake_payment
    
    monkeypatch.setattr(
        "app.modules.payments.facades.payments.webhook_handler.handle_payment_success",
        fake_handle_payment_success,
    )

    payload_dict = {"type": "checkout.session.completed"}
    raw_body = json.dumps(payload_dict).encode("utf-8")
    headers = {"stripe-signature": "fake_sig"}

    result = await handle_webhook(
        db,
        provider=PaymentProvider.STRIPE,
        raw_body=raw_body,
        headers=headers,
        payment_service=FakePaymentService(db),
        payment_repo=FakePaymentRepo(),
        refund_service=FakeRefundService(db),
        refund_repo=FakeRefundRepo(),
        event_service=FakeEventSvc(None),
    )
    
    assert result["status"] == "ok"
    assert result["event"] == "payment_succeeded"
    assert result["payment_id"] == 222


@pytest.mark.asyncio
async def test_handle_webhook_idempotent_skip_when_already_processed(monkeypatch, db, make_payment):
    class FakePaymentService:
        def __init__(self, session): 
            self.session = session

    class FakePaymentRepo:
        async def get_by_id(self, session, payment_id):
            return make_payment(id=77)

    class FakeRefundService:
        def __init__(self, session): 
            self.session = session

    class FakeRefundRepo:
        pass

    class FakeEventSvc:
        def __init__(self, repo): 
            self.repo = repo
        async def register_event(self, session, payment_id, provider_event_id, event_type, payload):
            event = type("Event", (), {"id": 444, "processed": True, "event_payload": payload})()
            return event

    # Mockear verificación de firma PayPal (debe ser async)
    async def fake_verify(provider, raw_body, headers):
        return True
    
    monkeypatch.setattr(
        "app.modules.payments.facades.payments.webhook_handler.verify_webhook_signature",
        fake_verify,
    )

    # Mockear normalización de webhook - evento que no es success/failure/refund
    class FakeNormalized:
        def __init__(self):
            self.payment_id = 77
            self.event_id = "pp_evt_1"
            self.event_type = "PAYMENT.CAPTURE.COMPLETED"
            self.raw = {"event_type": "PAYMENT.CAPTURE.COMPLETED"}
            self.is_success = False
            self.is_failure = False
            self.is_refund = False
            self.failure_reason = None
            self.provider_payment_id = None

    monkeypatch.setattr(
        "app.modules.payments.facades.payments.webhook_handler.normalize_webhook_payload",
        lambda provider, raw_body, headers: FakeNormalized(),
    )

    payload_dict = {"event_type": "PAYMENT.CAPTURE.COMPLETED"}
    raw_body = json.dumps(payload_dict).encode("utf-8")
    headers = {"paypal-signature": "fake_sig"}

    result = await handle_webhook(
        db,
        provider=PaymentProvider.PAYPAL,
        raw_body=raw_body,
        headers=headers,
        payment_service=FakePaymentService(db),
        payment_repo=FakePaymentRepo(),
        refund_service=FakeRefundService(db),
        refund_repo=FakeRefundRepo(),
        event_service=FakeEventSvc(None),
    )
    
    assert result["status"] == "ignored"
    assert result["event"] == "PAYMENT.CAPTURE.COMPLETED"


# Fin del archivo
