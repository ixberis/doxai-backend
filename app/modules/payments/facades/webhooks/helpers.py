
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/webhooks/helpers.py

Funciones helper para webhooks: clasificación de eventos y normalización legacy.

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from typing import Any, Dict

from app.modules.payments.enums import PaymentProvider
from .constants import (
    STRIPE_EVENT_SUCCESS,
    STRIPE_EVENT_FAILED,
    STRIPE_EVENT_REFUND,
    PAYPAL_EVENT_SUCCESS,
    PAYPAL_EVENT_FAILED,
    PAYPAL_EVENT_REFUND,
)


def is_success_event(provider: PaymentProvider, event_type: str) -> bool:
    """
    Determina si un evento de webhook es de éxito de pago.
    """
    if provider == PaymentProvider.STRIPE:
        return event_type in {
            "checkout.session.completed",
            "payment_intent.succeeded",
            "charge.succeeded",
        }
    elif provider == PaymentProvider.PAYPAL:
        return event_type in {
            "PAYMENT.CAPTURE.COMPLETED",
            "CHECKOUT.ORDER.APPROVED",
        }
    return False


def is_refund_event(provider: PaymentProvider, event_type: str) -> bool:
    """
    Determina si un evento de webhook es de reembolso.
    """
    if provider == PaymentProvider.STRIPE:
        return event_type in {
            "charge.refunded",
            "refund.created",
            "refund.updated",
            "refund.failed",
        }
    elif provider == PaymentProvider.PAYPAL:
        return event_type in {
            "PAYMENT.CAPTURE.REFUNDED",
            "PAYMENT.REFUND.COMPLETED",
            "PAYMENT.REFUND.FAILED",
        }
    return False


def normalize_webhook_data(provider: PaymentProvider, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza payload de webhook a formato común (legacy).
    
    Retorna:
        - provider_payment_id
        - provider_event_id
        - event_type
        - payment_id (si disponible)
    """
    if provider == PaymentProvider.STRIPE:
        return {
            "provider_payment_id": payload.get("data", {}).get("object", {}).get("payment_intent", ""),
            "provider_event_id": payload.get("id", ""),
            "event_type": payload.get("type", ""),
            "payment_id": payload.get("data", {}).get("object", {}).get("metadata", {}).get("payment_id"),
        }
    elif provider == PaymentProvider.PAYPAL:
        return {
            "provider_payment_id": payload.get("resource", {}).get("id", ""),
            "provider_event_id": payload.get("id", ""),
            "event_type": payload.get("event_type", ""),
            "payment_id": payload.get("resource", {}).get("custom_id"),
        }
    return {}


__all__ = [
    "is_success_event",
    "is_refund_event",
    "normalize_webhook_data",
]

# Fin del archivo backend/app/modules/payments/facades/webhooks/helpers.py
