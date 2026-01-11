# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/models/__init__.py

SSOT para modelos ORM de billing.
Este módulo NO importa services ni routers para evitar imports circulares.

Uso:
    from app.modules.billing.models import Wallet, CreditTransaction, CheckoutIntent

Autor: DoxAI
Fecha: 2026-01-11
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

__all__ = [
    # Credits models
    "Wallet",
    "CreditTransaction",
    "UsageReservation",
    # Checkout models
    "CheckoutIntent",
    "CheckoutIntentStatus",
]
