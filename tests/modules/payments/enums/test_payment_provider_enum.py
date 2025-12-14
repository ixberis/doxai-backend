# -*- coding: utf-8 -*-
from app.modules.payments.enums import PaymentProvider

def test_payment_provider_members_and_values_lowercase():
    assert PaymentProvider.STRIPE.value == "stripe"
    assert PaymentProvider.PAYPAL.value == "paypal"
    for p in PaymentProvider:
        assert p.value == p.value.lower()
# Fin del archivo