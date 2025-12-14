
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/adapters/refund_adapters.py

Adaptadores v3 para reembolsos Stripe y PayPal.
Versión limpia y alineada a Payment / Refund v3 (créditos prepagados).

Nota:
- Stub seguro (NO llama a Stripe/PayPal).
- Devuelve datos normalizados para RefundService.

Autor: Ixchel Beristáin
Fecha: 2025-11-21 (v3)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, Any, Optional

from app.modules.payments.enums import PaymentProvider, Currency, RefundStatus
from app.modules.payments.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)


# ============================================================================
# ADAPTADOR STRIPE (STUB)
# ============================================================================

async def create_stripe_refund(
    *,
    payment_intent_id: str,
    amount: Decimal,
    currency: Currency,
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea un refund en Stripe (stub seguro).
    """

    logger.warning(
        "⚠️ Stripe refund stub (v3) – NO se ejecuta refund real. payment_intent=%s",
        payment_intent_id,
    )

    fake_refund_id = f"stripe_refund_{payment_intent_id}_{idempotency_key or 'nokey'}"

    return {
        "provider_refund_id": fake_refund_id,
        "status": RefundStatus.REFUNDED.value,   # normalizamos al enum
        "created_at": utcnow(),
        "amount": str(amount),
        "currency": currency.value,
        "metadata": metadata or {},
        "_stub": True,
    }


# ============================================================================
# ADAPTADOR PAYPAL (STUB)
# ============================================================================

async def create_paypal_refund(
    *,
    order_id: str,
    amount: Decimal,
    currency: Currency,
    note: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Crea un refund en PayPal (stub).
    order_id: ID de orden o captura en PayPal.
    """

    logger.warning(
        "⚠️ PayPal refund stub (v3) – NO se ejecuta refund real. order_id=%s",
        order_id,
    )

    fake_refund_id = f"paypal_refund_{order_id}_{idempotency_key or 'nokey'}"

    return {
        "provider_refund_id": fake_refund_id,
        "status": RefundStatus.REFUNDED.value,   # normalizado
        "created_at": utcnow(),
        "amount": str(amount),
        "currency": currency.value,
        "metadata": metadata or {},
        "_stub": True,
    }


# ============================================================================
# EJECUCIÓN UNIFICADA
# ============================================================================

async def execute_refund(
    *,
    provider: PaymentProvider,
    payment_intent_id: Optional[str] = None,
    order_id: Optional[str] = None,
    amount: Decimal,
    currency: Currency,
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ejecuta un refund con el proveedor correspondiente en API v3.

    Parámetros:
        provider: STRIPE o PAYPAL
        payment_intent_id: usado para Stripe
        order_id: usado para PayPal
        amount: monto decimal a reembolsar
        currency: MXN | USD
        reason: motivo opcional
        metadata: metadata adicional
        idempotency_key: clave idempotente

    Retorna:
        dict con provider_refund_id, status, created_at, metadata
    """

    if provider == PaymentProvider.STRIPE:
        if not payment_intent_id:
            raise ValueError("payment_intent_id es requerido para Stripe refunds")

        return await create_stripe_refund(
            payment_intent_id=payment_intent_id,
            amount=amount,
            currency=currency,
            reason=reason,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )

    elif provider == PaymentProvider.PAYPAL:
        if not order_id:
            raise ValueError("order_id es requerido para PayPal refunds")

        return await create_paypal_refund(
            order_id=order_id,
            amount=amount,
            currency=currency,
            note=reason,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )

    else:
        raise ValueError(f"Proveedor no soportado: {provider}")


__all__ = [
    "create_stripe_refund",
    "create_paypal_refund",
    "execute_refund",
]

# Fin del archivo backend/app/modules/payments/adapters/refund_adapters.py