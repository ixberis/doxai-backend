# -*- coding: utf-8 -*-
import importlib

def test_enums_package_exports_symbols():
    enums = importlib.import_module("app.modules.payments.enums")
    expected = {
        "Currency",
        "PaymentProvider",
        "PaymentStatus",
        "ReservationStatus",
        "CreditTxType",
        "UserPlan",
    }
    missing = [name for name in expected if not hasattr(enums, name)]
    assert not missing, f"Faltan exportaciones en enums: {missing}"
# Fin del archivo