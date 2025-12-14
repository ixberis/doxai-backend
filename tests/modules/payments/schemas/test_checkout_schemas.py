# -*- coding: utf-8 -*-
import pytest
from decimal import Decimal
from pydantic import ValidationError
from app.modules.payments.enums import Currency, PaymentProvider
from app.modules.payments.schemas.checkout_schemas import (
    CheckoutRequest, CheckoutResponse
)

def test_checkout_request_valid():
    req = CheckoutRequest(
        provider=PaymentProvider.STRIPE,
        amount=Decimal("15.00"),
        currency=Currency.MXN,
        credits=150,
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        idempotency_key="abc123",
    )
    assert req.provider is PaymentProvider.STRIPE
    assert req.currency is Currency.MXN
    assert req.amount == Decimal("15.00")
    assert req.credits == 150

@pytest.mark.parametrize("amount,credits", [(Decimal("0"), 100), (Decimal("-1"), 100), (Decimal("100"), 0), (Decimal("100"), -5)])
def test_checkout_request_invalid_amount_or_credits(amount, credits):
    with pytest.raises(ValidationError):
        CheckoutRequest(
            provider=PaymentProvider.PAYPAL,
            amount=amount,
            currency=Currency.USD,
            credits=credits,
            success_url="https://ok/s",
            cancel_url="https://ok/c",
        )

def test_checkout_response_minimal_shape():
    res = CheckoutResponse(
        payment_id=42,
        provider=PaymentProvider.STRIPE,
        provider_info={
            "provider_session_id": "cs_test_123",
            "redirect_url": "https://pay/abc",
            "client_secret": "pi_secret_123",
        },
    )
    assert res.payment_id == 42
    assert res.provider is PaymentProvider.STRIPE
    assert res.provider_info.provider_session_id == "cs_test_123"
# Fin del archivo