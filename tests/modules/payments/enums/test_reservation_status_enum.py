# -*- coding: utf-8 -*-
from app.modules.payments.enums import ReservationStatus

def test_reservation_status_is_lowercase_and_has_minimum_states():
    expected = {"pending", "active", "expired", "consumed", "cancelled"}
    got = {m.value for m in ReservationStatus}
    assert expected.issubset(got)
    for m in ReservationStatus:
        assert m.value == m.value.lower()
# Fin del archivo