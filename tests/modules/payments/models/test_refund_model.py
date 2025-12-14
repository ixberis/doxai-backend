
# backend/tests/modules/payments/models/test_refund_model.py

from sqlalchemy import CheckConstraint, UniqueConstraint, Index
from app.modules.payments.models import Refund
from app.modules.payments.enums import RefundStatus, Currency, PaymentProvider

def test_tablename_schema_and_columns():
    t = Refund.__table__
    # Schema es opcional en entornos de test sin PostgreSQL
    # En producción sería "public", pero puede ser None en tests
    assert t.name == "refunds"

    for col in [
        "id", "payment_id", "provider", "provider_refund_id",
        "status", "currency", "amount_cents", "reason",
        "idempotency_key", "refund_metadata",
        "created_at", "updated_at", "refunded_at", "failed_at"
    ]:
        assert col in t.c

def test_constraints_and_indexes():
    t = Refund.__table__
    # UQ(provider, provider_refund_id)
    uq_provider_refund = any(
        isinstance(c, UniqueConstraint) and 
        set(col.name for col in c.columns) == {"provider", "provider_refund_id"}
        for c in t.constraints
    )
    assert uq_provider_refund, f"Missing UQ(provider, provider_refund_id). Found constraints: {[c for c in t.constraints if isinstance(c, UniqueConstraint)]}"
    # UQ(payment_id, idempotency_key)
    uq_payment_idempotency = any(
        isinstance(c, UniqueConstraint) and 
        set(col.name for col in c.columns) == {"payment_id", "idempotency_key"}
        for c in t.constraints
    )
    assert uq_payment_idempotency, f"Missing UQ(payment_id, idempotency_key)"
    # CHECK monto positivo
    assert any(isinstance(c, CheckConstraint) and "amount_cents > 0" in str(c.sqltext) for c in t.constraints)
    # Índices
    idx_names = {i.name for i in t.indexes if isinstance(i, Index)}
    for expected in {"ix_refund_payment_status", "ix_refund_created_at", "ix_refund_payment_created"}:
        assert expected in idx_names

def test_helper_methods_mark_transitions():
    r = Refund(
        payment_id=1,
        provider=PaymentProvider.STRIPE,
        provider_refund_id="re_123",
        status=RefundStatus.PENDING,
        currency=Currency.MXN,
        amount_cents=500,
    )

    # mark_refunded
    r.mark_refunded(meta={"a": 1})
    assert r.status is RefundStatus.REFUNDED
    assert r.refunded_at is not None
    assert r.refund_metadata and r.refund_metadata.get("a") == 1

    # mark_failed
    r2 = Refund(
        payment_id=1,
        provider=PaymentProvider.PAYPAL,
        provider_refund_id="pp_789",
        status=RefundStatus.PENDING,
        currency=Currency.MXN,
        amount_cents=700,
    )
    r2.mark_failed(error="denied")
    assert r2.status is RefundStatus.FAILED
    assert r2.failed_at is not None
    assert r2.refund_metadata and r2.refund_metadata.get("error") == "denied"

    # mark_cancelled
    r3 = Refund(
        payment_id=1,
        provider=PaymentProvider.STRIPE,
        provider_refund_id="",
        status=RefundStatus.PENDING,
        currency=Currency.MXN,
        amount_cents=300,
    )
    r3.mark_cancelled(provider_refund_id="re_cancel", meta={"reason": "user_request"})
    assert r3.status is RefundStatus.CANCELLED
    assert r3.provider_refund_id == "re_cancel"
    assert r3.refund_metadata and r3.refund_metadata.get("reason") == "user_request"
# end of backend/tests/modules/payments/models/test_refund_model.py