
# backend/tests/modules/payments/facades/checkout/test_provider_sessions.py
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import HTTPException

from app.modules.payments.enums import PaymentProvider, Currency
from app.modules.payments.facades.checkout.provider_sessions import (
    generate_idempotency_key,
    create_provider_session,
)

def test_generate_idempotency_key_is_stable():
    k1 = generate_idempotency_key(
        user_id="user-123",
        provider=PaymentProvider.STRIPE,
        amount_cents=19900,
        credits_purchased=100,
        success_url="https://app.doxai.mx/ok",
        cancel_url="https://app.doxai.mx/cancel",
        client_nonce="n-1",
    )
    k2 = generate_idempotency_key(
        user_id="user-123",
        provider=PaymentProvider.STRIPE,
        amount_cents=19900,
        credits_purchased=100,
        success_url="https://app.doxai.mx/ok",
        cancel_url="https://app.doxai.mx/cancel",
        client_nonce="n-1",
    )
    assert isinstance(k1, str) and len(k1) >= 16
    assert k1 == k2

def test_generate_idempotency_key_changes_with_input():
    a = generate_idempotency_key(
        user_id="user-123",
        provider=PaymentProvider.STRIPE,
        amount_cents=19900,
        credits_purchased=100,
        success_url="https://app.doxai.mx/ok",
        cancel_url="https://app.doxai.mx/cancel",
        client_nonce="nonce-a",
    )
    b = generate_idempotency_key(
        user_id="user-123",
        provider=PaymentProvider.STRIPE,
        amount_cents=19900,
        credits_purchased=100,
        success_url="https://app.doxai.mx/ok",
        cancel_url="https://app.doxai.mx/cancel",
        client_nonce="nonce-b",
    )
    assert a != b

@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [PaymentProvider.STRIPE, PaymentProvider.PAYPAL])
async def test_create_provider_session_ok(provider, monkeypatch):
    monkeypatch.setenv("PAYMENTS_ENV", "test")
    provider_payment_id, url, expires_at = await create_provider_session(
        provider=provider,
        user_id="user-123",
        currency=Currency.MXN,
        credits_purchased=25,
        amount_cents=12500,
        idempotency_key=generate_idempotency_key(
            user_id="user-123",
            provider=provider,
            amount_cents=12500,
            credits_purchased=25,
            success_url="https://app.doxai.mx/ok",
            cancel_url="https://app.doxai.mx/cancel",
            client_nonce="xyz",
        ),
        success_url="https://app.doxai.mx/ok",
        cancel_url="https://app.doxai.mx/cancel",
        metadata={"test": True},
    )
    assert isinstance(provider_payment_id, str) and len(provider_payment_id) > 8
    assert isinstance(url, str) and url.startswith("http")
    assert isinstance(expires_at, datetime) and expires_at.tzinfo is not None
    now = datetime.now(timezone.utc)
    # Tu stub expira ~24h; permitimos margen hasta 36h
    assert expires_at > now and expires_at - now < timedelta(hours=36)

@pytest.mark.asyncio
async def test_create_provider_session_unsupported_provider():
    class FakeProv(str): pass
    with pytest.raises((HTTPException, ValueError)):
        await create_provider_session(
            provider=FakeProv("otro"),
            user_id="user-1",
            currency=Currency.USD,
            credits_purchased=1,
            amount_cents=100,
            idempotency_key="x",
            success_url="https://app.doxai.mx/ok",
            cancel_url="https://app.doxai.mx/cancel",
            metadata=None,
        )

# Fin del archivo backend/tests/modules/payments/facades/checkout/test_provider_sessions.py


