
## -*- coding: utf-8 -*-
"""
backend\app\modules\payments\facades\payments\refunds\refund_provider.py

Simulación de reembolso con PayPal/Stripe.

IMPORTANTE:
Este archivo es un stub seguro: no llama a proveedores reales.
La integración se completará en una fase posterior.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional


async def provider_refund_stub(
    *,
    payment_id: int,
    amount: Decimal,
) -> tuple[str, bool]:
    """
    Simula la creación de un refund con un proveedor externo.
    Devuelve una tupla (provider_refund_id, is_confirmed).
    
    - is_confirmed=True: el refund fue confirmado inmediatamente (succeeded)
    - is_confirmed=False: el refund está pendiente (pending), esperando webhook
    """
    return (f"refund_provider_{payment_id}", True)

# Fin del archivo backend\app\modules\payments\facades\payments\refunds\refund_provider.py