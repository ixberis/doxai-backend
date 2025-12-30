# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/webhooks/__init__.py

Webhooks de billing para procesar notificaciones de pago.

Autor: DoxAI
Fecha: 2025-12-29
"""

from .stripe_handler import (
    handle_stripe_checkout_completed,
    verify_stripe_webhook_signature,
)

__all__ = [
    "handle_stripe_checkout_completed",
    "verify_stripe_webhook_signature",
]
