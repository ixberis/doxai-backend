# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/models/__init__.py

SSOT para modelos ORM de billing.
Este módulo NO importa services ni routers para evitar imports circulares.

Uso:
    from app.modules.billing.models import Wallet, CreditTransaction, CheckoutIntent

Autor: DoxAI
Fecha: 2026-01-11
Updated: 2026-01-12 - Added SSOT assertions for CheckoutIntent
"""

from app.modules.billing.credits.models import (
    Wallet,
    CreditTransaction,
    UsageReservation,
)

from app.modules.billing.models.checkout_intent import (
    CheckoutIntent,
    CheckoutIntentStatus,
)

from app.modules.billing.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    CurrencyEnum,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SSOT ASSERTION: CheckoutIntent must NOT have user_id column
# This assertion runs at import time to catch misconfigurations early
# ═══════════════════════════════════════════════════════════════════════════════
def _assert_checkout_intent_ssot():
    """
    Validate CheckoutIntent model has correct SSOT columns.
    Runs at import time to fail fast if there's a regression.
    """
    from sqlalchemy.inspection import inspect
    
    mapper = inspect(CheckoutIntent)
    column_names = {col.key for col in mapper.columns}
    
    if "user_id" in column_names:
        raise RuntimeError(
            "SSOT VIOLATION: CheckoutIntent ORM contains 'user_id' column! "
            f"Columns found: {sorted(column_names)}. "
            "This will cause INSERT failures in production. "
            "Remove user_id from the model definition."
        )
    
    if "auth_user_id" not in column_names:
        raise RuntimeError(
            "SSOT VIOLATION: CheckoutIntent ORM missing 'auth_user_id' column! "
            f"Columns found: {sorted(column_names)}. "
            "Add auth_user_id to the model definition."
        )


# Run assertion at import time
_assert_checkout_intent_ssot()


__all__ = [
    # Credits models
    "Wallet",
    "CreditTransaction",
    "UsageReservation",
    # Checkout models
    "CheckoutIntent",
    "CheckoutIntentStatus",
    # Payment models
    "Payment",
    "PaymentProvider",
    "PaymentStatus",
    "CurrencyEnum",
]
