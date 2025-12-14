
# backend/tests/modules/payments/facades/payments/test_refunds_flow.py
import pytest
from datetime import datetime, timezone
from fastapi import HTTPException

from app.modules.payments.facades.payments import refund
from app.modules.payments.enums import PaymentStatus, PaymentProvider, Currency, RefundStatus

def _now():
    return datetime.now(timezone.utc)


class _RefObj:
    """Fake Refund con las mismas APIs usadas por la fachada."""
    def __init__(self, rid=1001):
        self.id = rid
        self.status = RefundStatus.PENDING
        self.provider_refund_id = None
        self.refund_metadata = {}
        self._failed = False
        self._cancelled = False
        self._refunded = False

    def mark_refunded(self, provider_refund_id=None, meta=None):
        self.status = RefundStatus.REFUNDED
        self.provider_refund_id = provider_refund_id
        self.refund_metadata = (self.refund_metadata or {}) | (meta or {})
        self._refunded = True

    def mark_failed(self, error=""):
        self.status = RefundStatus.FAILED
        self.refund_metadata = (self.refund_metadata or {}) | {"error": error}
        self._failed = True

    def mark_cancelled(self, provider_refund_id=None, meta=None):
        self.status = RefundStatus.CANCELLED
        self.provider_refund_id = provider_refund_id
        self.refund_metadata = (self.refund_metadata or {}) | (meta or {})
        self._cancelled = True


@pytest.mark.asyncio
async def test_refund_full_success_reverses_all_credits_and_marks_payment_refunded(
    monkeypatch, db, make_payment
):
    """Reembolso total: proveedor 'succeeded' → revertir todos los créditos y Payment=REFUNDED."""
    pay = make_payment(
        id=10,
        user_id=77,
        amount_cents=20000,
        currency=Currency.USD,
        status=PaymentStatus.SUCCEEDED,
        credits_purchased=200,
        provider=PaymentProvider.STRIPE,
        provider_payment_id="pi_abc",
        provider_transaction_id="ch_xyz",
        payment_metadata={"credits_reversed_total": 0},
    )

    # Fakes / spies
    class FakePaymentSvc:
        def __init__(self, *args, **kwargs): ...
        async def get_payment_by_id(self, session, pid): return pay
        async def update_payment_status(self, payment_id, new_status, payment_metadata, refunded_at=None):
            assert new_status == PaymentStatus.REFUNDED
            pay.status = new_status
            pay.payment_metadata = payment_metadata
            return pay

    credits_called = {"count": 0, "credits": 0}
    class FakeCreditSvc:
        def __init__(self, *args, **kwargs): ...
        async def consume_credits(self, user_id, credits, operation_code, idempotency_key, metadata):
            credits_called["count"] += 1
            credits_called["credits"] = credits
            class Bal: balance = 300
            return Bal(), [{"delta": -credits}]

    class FakeRefundSvc:
        def __init__(self, *args, **kwargs): ...
        async def find_by_idempotency_key(self, **kwargs): return None
        async def validate_refund_limits(self, payment, refund_amount): return True
        async def create_refund(self, *args, **kwargs): return _RefObj(rid=5001)

    async def fake_execute_refund(**kwargs):
        # Stub de proveedor: retorna (provider_refund_id, is_confirmed)
        return ("re_123", True)

    # Patch de servicios donde la función refund() los construye
    import app.modules.payments.facades.payments.refunds as refunds_mod
    monkeypatch.setattr(refunds_mod, "PaymentService", FakePaymentSvc)
    monkeypatch.setattr(refunds_mod, "CreditService", FakeCreditSvc)
    monkeypatch.setattr(refunds_mod, "RefundService", FakeRefundSvc)
    
    # Patch del stub de proveedor (parchear en el módulo refund_provider)
    import app.modules.payments.facades.payments.refunds.refund_provider as refund_provider_mod
    monkeypatch.setattr(refund_provider_mod, "provider_refund_stub", fake_execute_refund)

    r, updated = await refund(db, payment_id=10)

    assert r.status == PaymentStatus.REFUNDED
    assert r.provider_refund_id == "re_123"
    assert updated.status == PaymentStatus.REFUNDED
    assert credits_called["count"] == 1
    assert credits_called["credits"] == 200  # todos


@pytest.mark.asyncio
async def test_refund_partial_success_reverses_proportional_and_keeps_payment_paid(
    monkeypatch, db, make_payment
):
    """Reembolso parcial: reversa proporcional de créditos y Payment queda SUCCEEDED."""
    pay = make_payment(
        id=11,
        user_id=88,
        amount_cents=10000,
        currency=Currency.USD,
        status=PaymentStatus.SUCCEEDED,
        credits_purchased=100,
        provider=PaymentProvider.STRIPE,
        provider_payment_id="pi_111",
        provider_transaction_id="ch_111",
        payment_metadata={"credits_reversed_total": 10},  # ya se revirtieron 10 antes
    )

    class FakePaymentSvc:
        def __init__(self, *args, **kwargs): ...
        async def get_payment_by_id(self, session, pid): return pay
        async def update_payment_status(self, payment_id, new_status, payment_metadata, refunded_at=None):
            # Parcial → PaymentStatus.SUCCEEDED
            assert new_status == PaymentStatus.SUCCEEDED
            pay.status = new_status
            pay.payment_metadata = payment_metadata
            return pay

    credits_called = {"credits": 0}
    class FakeCreditSvc:
        def __init__(self, *args, **kwargs): ...
        async def consume_credits(self, user_id, credits, operation_code, idempotency_key, metadata):
            credits_called["credits"] = credits
            class Bal: balance = 275
            return Bal(), [{"delta": -credits}]

    class FakeRefundSvc:
        def __init__(self, *args, **kwargs): ...
        async def find_by_idempotency_key(self, **kwargs): return None
        async def validate_refund_limits(self, payment, refund_amount): return True
        async def create_refund(self, *args, **kwargs): return _RefObj(rid=6001)

    async def fake_execute_refund(**kwargs):
        return ("re_par", True)

    import app.modules.payments.facades.payments.refunds as refunds_mod
    import app.modules.payments.facades.payments.refunds.refund_provider as refund_provider_mod
    monkeypatch.setattr(refunds_mod, "PaymentService", FakePaymentSvc)
    monkeypatch.setattr(refunds_mod, "CreditService", FakeCreditSvc)
    monkeypatch.setattr(refunds_mod, "RefundService", FakeRefundSvc)
    monkeypatch.setattr(refund_provider_mod, "provider_refund_stub", fake_execute_refund)

    # amount 2500/10000 → 25% → 25 créditos; remaining=90 → 25
    r, updated = await refund(db, payment_id=11, amount_cents=2500)

    assert r.status == PaymentStatus.REFUNDED
    assert updated.status == PaymentStatus.SUCCEEDED
    assert credits_called["credits"] == 25


@pytest.mark.asyncio
async def test_refund_pending_does_not_reverse_credits(monkeypatch, db, make_payment):
    """Proveedor 'pending' → no revertir créditos; se espera webhook posterior."""
    pay = make_payment(
        id=12,
        user_id=99,
        amount_cents=5000,
        currency=Currency.USD,
        status=PaymentStatus.SUCCEEDED,
        credits_purchased=50,
        provider=PaymentProvider.PAYPAL,
        provider_payment_id="PP-1",
        provider_transaction_id="CAP-1",
        payment_metadata={},
    )

    class FakePaymentSvc:
        def __init__(self, *args, **kwargs): ...
        async def get_payment_by_id(self, session, pid): return pay
        async def update_payment_status(self, **kwargs): return pay

    class FakeCreditSvc:
        def __init__(self, *args, **kwargs): ...
        async def consume_credits(self, *a, **k):
            raise AssertionError("No debe consumirse créditos en pending")

    class FakeRefundSvc:
        def __init__(self, *args, **kwargs): ...
        async def find_by_idempotency_key(self, **kwargs): return None
        async def validate_refund_limits(self, *a, **k): return True
        async def create_refund(self, *args, **kwargs): return _RefObj(rid=7001)

    async def fake_execute_refund(**kwargs):
        # Pending: retorna (refund_id, False) para indicar que NO está confirmado
        return ("re_pending", False)

    import app.modules.payments.facades.payments.refunds as refunds_mod
    import app.modules.payments.facades.payments.refunds.refund_provider as refund_provider_mod
    monkeypatch.setattr(refunds_mod, "PaymentService", FakePaymentSvc)
    monkeypatch.setattr(refunds_mod, "CreditService", FakeCreditSvc)
    monkeypatch.setattr(refunds_mod, "RefundService", FakeRefundSvc)
    monkeypatch.setattr(refund_provider_mod, "provider_refund_stub", fake_execute_refund)

    r, updated = await refund(db, payment_id=12, amount_cents=1000)

    assert r.status != RefundStatus.REFUNDED  # pending mantiene PENDING en el refund fake
    assert updated.id == 12  # no cambia estado de payment en esta fase


@pytest.mark.asyncio
async def test_refund_failed_raises_and_marks_failed(monkeypatch, db, make_payment):
    pay = make_payment(
        id=13, user_id=1, amount_cents=1000, currency=Currency.USD,
        status=PaymentStatus.SUCCEEDED, credits_purchased=10,
        provider=PaymentProvider.STRIPE, provider_payment_id="pi_x", provider_transaction_id="ch_x"
    )

    class FakePaymentSvc:
        def __init__(self, *args, **kwargs): ...
        async def get_payment_by_id(self, session, pid): return pay

    class FakeCreditSvc:
        def __init__(self, *args, **kwargs): ...

    class FakeRefundSvc:
        def __init__(self, *args, **kwargs): ...
        async def find_by_idempotency_key(self, **kwargs): return None
        async def validate_refund_limits(self, *a, **k): return True
        async def create_refund(self, *args, **kwargs): return _RefObj(rid=8001)

    async def fake_execute_refund(**kwargs):
        raise HTTPException(status_code=500, detail="Reembolso falló en proveedor: card_declined")

    import app.modules.payments.facades.payments.refunds as refunds_mod
    import app.modules.payments.facades.payments.refunds.refund_provider as refund_provider_mod
    monkeypatch.setattr(refunds_mod, "PaymentService", FakePaymentSvc)
    monkeypatch.setattr(refunds_mod, "CreditService", FakeCreditSvc)
    monkeypatch.setattr(refunds_mod, "RefundService", FakeRefundSvc)
    monkeypatch.setattr(refund_provider_mod, "provider_refund_stub", fake_execute_refund)

    with pytest.raises(HTTPException) as ex:
        await refund(db, payment_id=13, amount_cents=500)
    assert ex.value.status_code == 500


@pytest.mark.asyncio
async def test_refund_cancelled_raises_and_marks_cancelled(monkeypatch, db, make_payment):
    pay = make_payment(
        id=14, user_id=1, amount_cents=1000, currency=Currency.USD,
        status=PaymentStatus.SUCCEEDED, credits_purchased=10,
        provider=PaymentProvider.PAYPAL, provider_payment_id="PP-2", provider_transaction_id="CAP-2"
    )

    class FakePaymentSvc:
        def __init__(self, *args, **kwargs): ...
        async def get_payment_by_id(self, session, pid): return pay

    class FakeRefundSvc:
        def __init__(self, *args, **kwargs): ...
        async def find_by_idempotency_key(self, **kwargs): return None
        async def validate_refund_limits(self, *a, **k): return True
        async def create_refund(self, *args, **kwargs): return _RefObj(rid=9001)

    async def fake_execute_refund(**kwargs):
        raise HTTPException(status_code=400, detail="Reembolso cancelado por el proveedor")

    import app.modules.payments.facades.payments.refunds as refunds_mod
    import app.modules.payments.facades.payments.refunds.refund_provider as refund_provider_mod
    monkeypatch.setattr(refunds_mod, "PaymentService", FakePaymentSvc)
    monkeypatch.setattr(refunds_mod, "RefundService", FakeRefundSvc)
    monkeypatch.setattr(refund_provider_mod, "provider_refund_stub", fake_execute_refund)

    with pytest.raises(HTTPException) as ex:
        await refund(db, payment_id=14, amount_cents=500)
    assert ex.value.status_code == 400


@pytest.mark.asyncio
async def test_refund_idempotent_returns_existing_and_skips_adapter(monkeypatch, db, make_payment):
    pay = make_payment(
        id=15, user_id=1, amount_cents=1000, currency=Currency.USD,
        status=PaymentStatus.SUCCEEDED, credits_purchased=10,
        provider=PaymentProvider.STRIPE, provider_payment_id="pi_15", provider_transaction_id="ch_15"
    )
    existing_ref = _RefObj(rid=1515)
    existing_ref.status = RefundStatus.REFUNDED

    class FakePaymentSvc:
        def __init__(self, *args, **kwargs): ...
        async def get_payment_by_id(self, session, pid): return pay

    class FakeRefundSvc:
        def __init__(self, *args, **kwargs): ...
        async def validate_refund_limits(self, *a, **k): return True
        async def find_by_idempotency_key(self, payment_id, idempotency_key):
            assert idempotency_key == "idem-1"
            return existing_ref

    def _should_not_be_called(*a, **k):
        raise AssertionError("execute_provider_refund no debe llamarse en idempotencia")

    import app.modules.payments.facades.payments.refunds as refunds_mod
    import app.modules.payments.facades.payments.refunds.refund_provider as refund_provider_mod
    monkeypatch.setattr(refunds_mod, "PaymentService", FakePaymentSvc)
    monkeypatch.setattr(refunds_mod, "RefundService", FakeRefundSvc)
    monkeypatch.setattr(refund_provider_mod, "provider_refund_stub", _should_not_be_called)

    r, p = await refund(db, payment_id=15, amount_cents=1000, idempotency_key="idem-1")
    assert r.id == 1515
    assert p.id == 15


@pytest.mark.asyncio
async def test_refund_credit_reversal_failure_does_not_break_flow(monkeypatch, db, make_payment):
    """Si fallan los créditos (p.ej. saldo insuficiente), el reembolso no debe fallar."""
    pay = make_payment(
        id=16,
        user_id=2,
        amount_cents=10000,
        currency=Currency.USD,
        status=PaymentStatus.SUCCEEDED,
        credits_purchased=100,
        provider=PaymentProvider.STRIPE,
        provider_payment_id="pi_16",
        provider_transaction_id="ch_16",
        payment_metadata={"credits_reversed_total": 0},
    )

    class FakePaymentSvc:
        def __init__(self, *args, **kwargs): ...
        async def get_payment_by_id(self, session, pid): return pay
        async def update_payment_status(self, payment_id, new_status, payment_metadata, refunded_at=None):
            pay.status = PaymentStatus.REFUNDED
            pay.payment_metadata = payment_metadata
            return pay

    class FakeCreditSvc:
        def __init__(self, *args, **kwargs): ...
        async def consume_credits(self, *a, **k):
            raise HTTPException(status_code=422, detail="Saldo insuficiente")

    class FakeRefundSvc:
        def __init__(self, *args, **kwargs): ...
        async def find_by_idempotency_key(self, **kwargs): return None
        async def validate_refund_limits(self, *a, **k): return True
        async def create_refund(self, *args, **kwargs): return _RefObj(rid=16001)

    async def fake_execute_refund(**kwargs):
        return ("re_ok", True)

    import app.modules.payments.facades.payments.refunds as refunds_mod
    import app.modules.payments.facades.payments.refunds.refund_provider as refund_provider_mod
    monkeypatch.setattr(refunds_mod, "PaymentService", FakePaymentSvc)
    monkeypatch.setattr(refunds_mod, "CreditService", FakeCreditSvc)
    monkeypatch.setattr(refunds_mod, "RefundService", FakeRefundSvc)
    monkeypatch.setattr(refund_provider_mod, "provider_refund_stub", fake_execute_refund)

    r, updated = await refund(db, payment_id=16)  # total

    assert r.status == PaymentStatus.REFUNDED
    assert updated.status == PaymentStatus.REFUNDED
    # El metadata de fallo de créditos se guarda en payment.payment_metadata, no en refund
    assert updated.payment_metadata.get("credits_reversal_failed") is True
    assert "credits_reversal_error" in updated.payment_metadata
# Fin del archivo backend/tests/modules/payments/facades/payments/test_refunds_flow.py
