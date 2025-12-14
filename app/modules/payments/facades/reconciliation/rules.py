
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/reconciliation/rules.py

Reglas de normalización y validación para reconciliación.

Autor: Ixchel Beristáin
Fecha: 26/10/2025 (ajustado 20/11/2025)
"""

from typing import Optional

from app.modules.payments.enums import PaymentProvider, PaymentStatus


def normalize_provider_status(
    provider: PaymentProvider,
    status: str,
) -> Optional[PaymentStatus]:
    """
    Normaliza el status del proveedor a nuestro enum PaymentStatus.
    """
    if not status:
        return None

    status_lower = status.lower()

    if provider == PaymentProvider.STRIPE:
        if status_lower in ["succeeded", "paid"]:
            return PaymentStatus.SUCCEEDED
        elif status_lower in ["pending", "processing"]:
            return PaymentStatus.PENDING
        elif status_lower == "failed":
            return PaymentStatus.FAILED
        elif status_lower in ["canceled", "cancelled"]:
            return PaymentStatus.CANCELLED
        elif status_lower == "refunded":
            return PaymentStatus.REFUNDED

    elif provider == PaymentProvider.PAYPAL:
        if status_lower in ["completed", "approved"]:
            return PaymentStatus.SUCCEEDED
        elif status_lower in ["pending", "created"]:
            return PaymentStatus.PENDING
        elif status_lower in ["failed", "denied"]:
            return PaymentStatus.FAILED
        elif status_lower == "cancelled":
            return PaymentStatus.CANCELLED
        elif status_lower == "refunded":
            return PaymentStatus.REFUNDED

    return None


__all__ = ["normalize_provider_status"]

# Fin del archivo backend/app/modules/payments/facades/reconciliation/rules.py
