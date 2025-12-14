# -*- coding: utf-8 -*-
import importlib

def test_schemas_package_exports_symbols():
    pkg = importlib.import_module("app.modules.payments.schemas")

    # Schemas v3 alineados al modelo de créditos
    expected = [
        # common
        "PageMeta",
        # checkout
        "CheckoutRequest", "CheckoutResponse", "ProviderCheckoutInfo",
        # wallet
        "WalletOut",
        # refund
        "RefundCreate", "RefundOut",
        # reservation
        "UsageReservationCreate", "UsageReservationOut",
    ]
    missing = [name for name in expected if not hasattr(pkg, name)]
    assert not missing, f"Faltan exports en schemas: {missing}"
# Fin del archivo