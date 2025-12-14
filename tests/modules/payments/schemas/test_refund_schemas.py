# -*- coding: utf-8 -*-
import pytest
from pydantic import ValidationError
from app.modules.payments.enums import PaymentProvider, Currency
from app.modules.payments.schemas.refund_schemas import RefundCreate, RefundOut

def test_refund_create_valid():
    from decimal import Decimal
    r = RefundCreate(
        payment_id=5,
        amount=Decimal("5.00"),
        reason="user_request",
    )
    assert r.amount == Decimal("5.00")
    assert r.payment_id == 5

@pytest.mark.parametrize("amount", ["0", "-1"])
def test_refund_create_invalid_amount(amount):
    from decimal import Decimal
    with pytest.raises(ValidationError):
        RefundCreate(
            payment_id=5,
            amount=Decimal(amount),
        )

def test_refund_out_shape_minimal():
    """
    Test de RefundOut con el enum v3.
    
    En v3, RefundStatus usa REFUNDED en lugar de COMPLETED.
    """
    from datetime import datetime, timezone
    from decimal import Decimal
    from app.modules.payments.enums import RefundStatus
    out = RefundOut(
        id=10,
        payment_id=5,
        currency=Currency.MXN,
        amount=Decimal("5.00"),
        credits_reversed=50,
        status=RefundStatus.REFUNDED,  # v3: REFUNDED en vez de COMPLETED
        provider_refund_id="re_123",
        created_at=datetime.now(timezone.utc),
    )
    assert out.id == 10
    assert out.payment_id == 5
    assert out.amount == Decimal("5.00")
    assert out.credits_reversed == 50
    assert out.status == RefundStatus.REFUNDED
# Fin del archivo