
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/checkout/__init__.py

Punto de entrada del submódulo de checkout del módulo Payments.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from .dto import CheckoutRequest, CheckoutResponse, ProviderCheckoutInfo
from .start_checkout import start_checkout

__all__ = [
    "CheckoutRequest",
    "CheckoutResponse",
    "ProviderCheckoutInfo",
    "start_checkout",
]

# Fin del archivo backend/app/modules/payments/facades/checkout/__init__.py
