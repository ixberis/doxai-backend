
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/webhooks/__init__.py

Exporta las funciones clave de facades/webhooks.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from .normalize import normalize_webhook_payload
from .success import (
    handle_payment_success,
    handle_payment_failure,
    handle_payment_refund,
)
from .verify import (
    verify_stripe_signature,
    verify_paypal_signature,
)
from .helpers import (
    is_success_event,
    is_refund_event,
    normalize_webhook_data,
)
from .handler import verify_and_handle_webhook

__all__ = [
    "normalize_webhook_payload",
    "handle_payment_success",
    "handle_payment_failure",
    "handle_payment_refund",
    "verify_stripe_signature",
    "verify_paypal_signature",
    "is_success_event",
    "is_refund_event",
    "normalize_webhook_data",
    "verify_and_handle_webhook",
]

# Fin del archivo backend\app\modules\payments\facades\webhooks\__init__.py