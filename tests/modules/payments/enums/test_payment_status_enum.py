# -*- coding: utf-8 -*-
import pytest
from app.modules.payments.enums import PaymentStatus

def test_payment_status_core_members_exist():
    assert hasattr(PaymentStatus, "CREATED")
    assert hasattr(PaymentStatus, "PENDING")
    assert hasattr(PaymentStatus, "SUCCEEDED")
    assert hasattr(PaymentStatus, "REFUNDED")
    assert hasattr(PaymentStatus, "FAILED")
    assert hasattr(PaymentStatus, "CANCELLED")

@pytest.mark.parametrize("m", ["CREATED", "PENDING", "SUCCEEDED", "REFUNDED", "FAILED", "CANCELLED"])
def test_payment_status_values_are_lowercase(m):
    assert getattr(PaymentStatus, m).value == getattr(PaymentStatus, m).value.lower()
# Fin del archivo