# -*- coding: utf-8 -*-
import pytest
from pydantic import ValidationError
from app.modules.payments.enums import ReservationStatus
from app.modules.payments.schemas.reservation_schemas import (
    UsageReservationCreate, UsageReservationOut
)

def test_usage_reservation_create_valid():
    r = UsageReservationCreate(
        credits=25,
        ttl_minutes=30,
        operation_id="res_k1",
    )
    assert r.credits == 25
    assert r.ttl_minutes == 30

@pytest.mark.parametrize("credits", [0, -10])
def test_usage_reservation_create_invalid_credits(credits):
    with pytest.raises(ValidationError):
        UsageReservationCreate(
            credits=credits,
            ttl_minutes=30,
        )

def test_usage_reservation_out_status_is_enum():
    from datetime import datetime, timezone
    out = UsageReservationOut(
        id=1,
        status=ReservationStatus.PENDING,
        credits_reserved=10,
        operation_id="op_123",
        expires_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    assert out.status == ReservationStatus.PENDING
    assert out.credits_reserved == 10
# Fin del archivo