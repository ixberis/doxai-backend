
# -*- coding: utf-8 -*-
"""
backend\app\modules\payments\facades\payments\refunds\refunds_helpers.py

Helpers para refund dentro de la arquitectura nueva.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from decimal import Decimal


def compute_credits_from_amount(amount: Decimal, exchange_rate: Decimal = Decimal("1")) -> int:
    """
    Traduce un monto monetario a créditos a revertir.
    Para Fase 3 se asume 1:1, pero se deja parametrizable.
    """
    return int(amount * exchange_rate)

# Fin del archivo backend\app\modules\payments\facades\payments\refunds\refunds_helpers.py
