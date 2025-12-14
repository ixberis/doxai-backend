
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/schemas/__init__.py

Punto de entrada para los esquemas Pydantic del módulo Payments (API v3).

Incluye únicamente los contratos vigentes para:
- Checkout de créditos prepagados
- Wallet del usuario
- Reservas de créditos
- Reembolsos
- Metadatos de paginación

Autor: Ixchel Beristain
Fecha: 2025-11-21 (v3)
"""

from __future__ import annotations

from .common_schemas import PageMeta
from .checkout_schemas import CheckoutRequest, CheckoutResponse, ProviderCheckoutInfo
from .wallet_schemas import WalletOut
from .reservation_schemas import UsageReservationCreate, UsageReservationOut
from .refund_schemas import RefundCreate, RefundOut
from .payment_status_schemas import PaymentStatusResponse, FINAL_STATUSES  # FASE 2

__all__ = [
    "PageMeta",
    "CheckoutRequest",
    "CheckoutResponse",
    "ProviderCheckoutInfo",
    "WalletOut",
    "UsageReservationCreate",
    "UsageReservationOut",
    "RefundCreate",
    "RefundOut",
    "PaymentStatusResponse",  # FASE 2
    "FINAL_STATUSES",  # FASE 2
]

# Fin del archivo backend/app/modules/payments/schemas/__init__.py
