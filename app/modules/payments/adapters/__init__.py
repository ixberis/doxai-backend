# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/adapters/__init__.py

Adaptadores para integraciones con proveedores externos.
"""

from .refund_adapters import (
    create_stripe_refund,
    create_paypal_refund,
    execute_refund,
)

__all__ = [
    "create_stripe_refund",
    "create_paypal_refund",
    "execute_refund",
]
