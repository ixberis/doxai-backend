
# backend/tests/modules/payments/facades/payments/test_get_payment_intent.py
import os
import pytest
from app.modules.payments.facades.payments import get_payment_intent, PaymentIntentNotFound
from app.modules.payments.enums import PaymentProvider, Currency

@pytest.mark.asyncio
async def test_get_payment_intent_returns_payment_info(db, make_payment):
    fake_payment = make_payment(
        id=42,
        user_id="user123",
        provider=PaymentProvider.STRIPE,
        currency=Currency.USD,
        amount=100.50,
        credits_awarded=1000,
    )
    
    class FakeRepo:
        async def get(self, session, payment_id):
            return fake_payment if payment_id == 42 else None
    
    result = await get_payment_intent(
        db,
        payment_id=42,
        payment_repo=FakeRepo(),
    )
    
    assert result["payment_id"] == 42
    assert result["provider"] == PaymentProvider.STRIPE
    assert result["currency"] == Currency.USD
    assert result["credits_awarded"] == 1000

@pytest.mark.asyncio
async def test_get_payment_intent_raises_when_not_found(db):
    class FakeRepo:
        async def get(self, session, payment_id):
            return None
    
    with pytest.raises(PaymentIntentNotFound):
        await get_payment_intent(
            db,
            payment_id=999,
            payment_repo=FakeRepo(),
        )
# Fin del archivo backend/tests/modules/payments/facades/payments/test_get_payment_intent.py
