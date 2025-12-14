
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/models/__init__.py

Punto de entrada de modelos ORM del módulo Payments (v3).

Se exportan los modelos principales:
- Wallet
- CreditTransaction
- Payment
- Refund
- UsageReservation
- PaymentEvent

Además, se mantiene un alias legacy:
- PaymentRecord → Payment

para compatibilidad con código antiguo (Auth, tests) que aún
importa PaymentRecord. Internamente es el mismo modelo Payment.

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from .wallet_models import Wallet
from .credit_transaction_models import CreditTransaction
from .payment_models import Payment
from .refund_models import Refund
from .usage_reservation_models import UsageReservation
from .payment_event_models import PaymentEvent

# Alias legacy para compatibilidad:
# En v3 PaymentRecord es simplemente Payment.
PaymentRecord = Payment  # type: ignore

# Alias para compatibilidad con tests legacy que usan CreditWallet
CreditWallet = Wallet  # type: ignore


__all__ = [
    "Wallet",
    "CreditTransaction",
    "Payment",
    "Refund",
    "UsageReservation",
    "PaymentEvent",
    # Alias legacy
    "PaymentRecord",
    "CreditWallet",
]

# Fin del archivo backend/app/modules/payments/models/__init__.py
