
# backend/tests/modules/payments/facades/reconciliation/test_reconciliation_core.py
import pytest
from app.modules.payments.facades.reconciliation import (
    reconcile_provider_transactions, find_discrepancies, generate_reconciliation_report
)
from app.modules.payments.enums import PaymentProvider, PaymentStatus
from datetime import datetime, timezone, timedelta

class P:
    def __init__(self, id, payment_intent_id, amount_cents, status, created_at):
        self.id = id
        self.payment_intent_id = payment_intent_id  # Nombre correcto del campo en el modelo Payment
        self.amount_cents = amount_cents
        self.amount = amount_cents / 100.0  # El modelo Payment usa amount en unidades (float), no centavos
        self.status = status
        self.created_at = created_at
        self.user_id = 1
        self.currency = type("C", (), {"value":"usd"})()
        self.paid_at = None

@pytest.mark.asyncio
async def test_reconcile_provider_transactions_amount_and_status(monkeypatch, db):
    now = datetime.now(timezone.utc)
    internal = [
        P(1, "pi_ok", 10000, PaymentStatus.SUCCEEDED, now - timedelta(hours=1)),
        P(2, "pi_diff_amt", 10000, PaymentStatus.SUCCEEDED, now),
        P(3, "pi_diff_status", 10000, PaymentStatus.PENDING, now),
        P(4, "pi_only_db", 5000, PaymentStatus.SUCCEEDED, now),
    ]

    async def _fake_load_internal_payments(*a, **k):
        return internal

    monkeypatch.setattr(
        "app.modules.payments.facades.reconciliation.core.load_internal_payments",
        _fake_load_internal_payments,
    )

    provider_txs = [
        {"id": "pi_ok", "amount": 100.0, "currency":"usd", "status":"succeeded", "created_at": now.isoformat()},
        {"id": "pi_diff_amt", "amount": 90.0, "currency":"usd", "status":"succeeded", "created_at": now.isoformat()},
        {"id": "pi_diff_status", "amount": 100.0, "currency":"usd", "status":"pending", "created_at": now.isoformat()},
        {"id": "pi_only_provider", "amount": 12.34, "currency":"usd", "status":"succeeded", "created_at": now.isoformat()},
    ]

    result = await reconcile_provider_transactions(
        db,
        provider=PaymentProvider.STRIPE,
        provider_transactions=provider_txs,
    )

    d = result.to_dict()
    assert d["missing_in_db_count"] == 1  # pi_only_provider
    assert any(x["provider_payment_id"] == "pi_diff_amt" for x in d["amount_discrepancies"])
    assert any(x["provider_payment_id"] == "pi_diff_status" for x in d["status_discrepancies"])
    assert any(x["provider_payment_id"] == "pi_only_db" for x in d["missing_in_provider"])

@pytest.mark.asyncio
async def test_find_discrepancies_and_report(monkeypatch, db):
    now = datetime.now(timezone.utc)

    payments = [
        P(10, None, 10000, PaymentStatus.SUCCEEDED, now - timedelta(days=1)),    # succeeded sin provider id
        P(11, "P11", 10000, PaymentStatus.PENDING, now - timedelta(days=2)),# pending >24h
        P(12, "P12", 10000, PaymentStatus.FAILED, now),                     # failed con éxito
    ]

    async def _fake_load_internal_payments2(*a, **k):
        return payments

    async def _fake_has_success_events(_db, pid):
        return pid == 12

    # core.* para find_discrepancies
    monkeypatch.setattr(
        "app.modules.payments.facades.reconciliation.core.load_internal_payments",
        _fake_load_internal_payments2,
    )
    monkeypatch.setattr(
        "app.modules.payments.facades.reconciliation.core.has_success_events",
        _fake_has_success_events,
    )

    # report.* también usa load_internal_payments directamente
    monkeypatch.setattr(
        "app.modules.payments.facades.reconciliation.report.load_internal_payments",
        _fake_load_internal_payments2,
    )

    disc = await find_discrepancies(db, provider=PaymentProvider.PAYPAL)
    assert len(disc["succeeded_without_provider_id"]) == 1
    assert len(disc["pending_too_long"]) == 1
    assert len(disc["failed_with_success_events"]) == 1

    report = await generate_reconciliation_report(
        db,
        provider=PaymentProvider.PAYPAL,
        start_date=now - timedelta(days=7),
        end_date=now,
        include_matched=True,
    )
    assert "summary" in report and "discrepancies" in report
    assert report["summary"]["total_payments"] == 3
# Fin del archivo backend/tests/modules/payments/facades/reconciliation/test_reconciliation_core.py
