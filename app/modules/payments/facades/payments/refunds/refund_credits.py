
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/payments/refunds/refund_credits.py

Cálculo y ejecución de la reversa de créditos después de un reembolso:
- calcular_créditos_a_revertir(...)
- revertir_créditos(...)

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from fastapi import HTTPException
from app.modules.payments.models.payment_models import Payment
from app.modules.payments.services.credit_service import CreditService


def calcular_creditos_a_revertir(
    *,
    payment: Payment,
    refund_amount_cents: int,
    provider_confirmed: bool,
) -> int:
    """
    Determina cuántos créditos revertir (full/partial) según el monto de reembolso y lo ya revertido.
    """
    if not provider_confirmed:
        return 0

    payment_meta = payment.payment_metadata or {}
    credits_reversed_total = payment_meta.get("credits_reversed_total", 0)

    if refund_amount_cents == payment.amount_cents:
        # Reembolso total
        return max(payment.credits_purchased - credits_reversed_total, 0)

    # Reembolso parcial proporcional
    ratio = Decimal(refund_amount_cents) / Decimal(payment.amount_cents)
    credits_decimal = ratio * Decimal(payment.credits_purchased)
    credits_calculated = int(credits_decimal.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    credits_remaining = max(payment.credits_purchased - credits_reversed_total, 0)
    return min(credits_calculated, credits_remaining)


async def revertir_creditos(
    *,
    credit_service: CreditService,
    payment: Payment,
    refund_id: int,
    refund_amount_cents: int,
    credits_to_reverse: int,
    reason: Optional[str],
    idempotency_key: Optional[str],
) -> Tuple[Optional[object], Optional[object]]:
    """
    Ejecuta la reversa de créditos si hay créditos por revertir.
    Devuelve (balance, ledger) o (None, None) si no hay acción.
    """
    if credits_to_reverse <= 0:
        return None, None

    credit_idempotency_key = f"refund_reversal_{idempotency_key}" if idempotency_key else None
    try:
        balance, ledger = await credit_service.consume_credits(
            user_id=payment.user_id,
            credits=credits_to_reverse,
            operation_code="refund_reversal",
            idempotency_key=credit_idempotency_key,
            metadata={
                "refund_id": str(refund_id),
                "payment_id": str(payment.id),
                "refund_amount_cents": refund_amount_cents,
                "refund_reason": reason,
                "is_full_refund": (refund_amount_cents == payment.amount_cents),
            },
        )
        return balance, ledger
    except HTTPException as credit_error:
        # No re-lanzamos; el flujo de refund puede continuar marcando metadata
        payment.payment_metadata = (payment.payment_metadata or {}) | {
            "credits_reversal_failed": True,
            "credits_reversal_error": credit_error.detail,
            "credits_to_reverse": credits_to_reverse,
        }
        return None, None

# Fin del archivo backend\app\modules\payments\facades\payments\refunds\refund_credits.py