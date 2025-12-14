
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/payments/__init__.py

Superficie de exportación de las fachadas principales del submódulo Payments.

Incluye:
- get_payment_intent / PaymentIntentNotFound: consulta de intents/pagos
- handle_webhook / WebhookSignatureError: procesamiento de webhooks Stripe/PayPal

Nota:
- El subpaquete `refunds` (plural) agrupa las fachadas de refunds.
- Para compatibilidad con código y tests legacy que hacen:
      from app.modules.payments.facades.payments import refund
  se expone un alias:
      refund = refunds

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from .intents import get_payment_intent, get_payment_status, PaymentIntentNotFound
from .webhook_handler import handle_webhook, WebhookSignatureError
from .refunds import refund  # función principal de refunds
from . import refunds  # subpaquete completo de refunds

__all__ = [
    "get_payment_intent",
    "get_payment_status",  # FASE 2
    "PaymentIntentNotFound",
    "handle_webhook",
    "WebhookSignatureError",
    "refund",  # función principal
    "refunds",  # subpaquete (alias legacy)
]

# Fin del archivo backend/app/modules/payments/facades/payments/__init__.py