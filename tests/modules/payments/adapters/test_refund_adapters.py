
# backend/tests/modules/payments/adapters/test_refund_adapters.py
import pytest
from app.modules.payments.enums import PaymentProvider, Currency
from app.modules.payments.adapters.refund_adapters import execute_refund

@pytest.mark.parametrize("provider", [PaymentProvider.STRIPE, PaymentProvider.PAYPAL])
@pytest.mark.parametrize("amount_cents,currency", [(1000, Currency.MXN), (550, Currency.USD)])
@pytest.mark.asyncio
async def test_execute_refund_returns_shape(provider, amount_cents, currency):
    from decimal import Decimal
    
    # Convertir centavos a decimal
    amount = Decimal(amount_cents) / 100
    
    # Preparar kwargs según el proveedor
    kwargs = {
        "provider": provider,
        "amount": amount,
        "currency": currency,
        "reason": "requested_by_customer",
        "idempotency_key": "refund-user1-ord1",
        "metadata": {"order_id": "ord-1"},
    }
    
    if provider == PaymentProvider.STRIPE:
        kwargs["payment_intent_id"] = "pi_12345"
    else:  # PayPal
        kwargs["order_id"] = "order_12345"
    
    res = await execute_refund(**kwargs)
    
    assert isinstance(res, dict)
    for key in ("provider_refund_id", "status", "created_at", "amount", "currency"):
        assert key in res

    assert str(res["currency"]).lower() == currency.value.lower()
    # Verificar que el monto devuelto es correcto (como string del Decimal)
    assert Decimal(res["amount"]) == amount

    # Acepta 'refunded' (normalizado en v3)
    allowed = {"succeeded", "pending", "failed", "cancelled", "refunded"}
    assert res["status"] in allowed

@pytest.mark.asyncio
async def test_execute_refund_unsupported_provider():
    from decimal import Decimal
    
    class FakeProv(str): pass
    with pytest.raises(ValueError):
        await execute_refund(
            provider=FakeProv("otro"),
            payment_intent_id="pi_x",
            amount=Decimal("1.00"),
            currency=Currency.MXN,
            reason=None,
            idempotency_key="idemp-x",
            metadata=None,
        )

# Fin del archivo backend/tests/modules/payments/adapters/test_refund_adapters.py


