
# backend/tests/modules/payments/models/test_models_package_exports.py

import importlib

def test_package_exports_public_api():
    mod = importlib.import_module("app.modules.payments.models")
    exported = set(getattr(mod, "__all__", []))

    assert {
        "Payment",
        "PaymentRecord",
        "PaymentEvent",
        "CreditWallet",
        "CreditTransaction",
        "UsageReservation",
        "Refund",
    }.issubset(exported)

def test_paymentrecord_alias_of_payment():
    from app.modules.payments.models import Payment, PaymentRecord
    assert PaymentRecord is Payment
# end of backend/tests/modules/payments/models/test_models_package_exports.py