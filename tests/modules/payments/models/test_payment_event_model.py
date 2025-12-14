# backend/tests/modules/payments/models/test_payment_event_model.py

from sqlalchemy import inspect, UniqueConstraint, Index
from app.modules.payments.models import PaymentEvent

def test_tablename_and_columns():
    t = PaymentEvent.__table__
    assert t.name == "payment_events"
    # Columnas v3: id, payment_id, provider_event_id, event_type, payload_json, created_at
    for col in ["id", "payment_id", "provider_event_id", "event_type", "payload_json", "created_at"]:
        assert col in t.c

    # payment_id es NOT NULL
    assert not t.c.payment_id.nullable

def test_unique_and_indexes():
    t = PaymentEvent.__table__
    # En v3: UniqueConstraint sobre provider_event_id
    assert any(
        isinstance(c, UniqueConstraint) and "provider_event_id" in [col.name for col in c.columns]
        for c in t.constraints
    ), "provider_event_id debe tener UniqueConstraint"

def test_relationship_to_payment():
    mapper = inspect(PaymentEvent)
    rel = mapper.relationships["payment"]
    assert rel.key == "payment"
# end of backend/tests/modules/payments/models/test_payment_event_model.py