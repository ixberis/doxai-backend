
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/payments/intents.py

Facade para consultar información de un pago (intent)
y su estado actual (CREATED, PENDING, SUCCEEDED, FAILED).

FASE 2: Añadido get_payment_status para polling robusto del Frontend.

Autor: Ixchel Beristain
Fecha: 2025-11-20 (actualizado 2025-12-13)
"""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.enums import PaymentStatus
from app.modules.payments.schemas.payment_status_schemas import (
    PaymentStatusResponse,
    FINAL_STATUSES,
)


class PaymentIntentNotFound(Exception):
    pass


# Tiempo de retry configurable por ENV (default: 5 segundos)
DEFAULT_RETRY_SECONDS = int(os.getenv("PAYMENTS_POLL_RETRY_SECONDS", "5"))


async def get_payment_intent(
    session: AsyncSession,
    *,
    payment_id: int,
    payment_repo: PaymentRepository,
):
    """
    Obtiene el estado actual de un pago (intent).

    Útil para:
    - consultarlo desde frontend,
    - debugging,
    - polling,
    - mostrar estado en pantallas de confirmación.
    """
    payment = await payment_repo.get(session, payment_id)
    if not payment:
        raise PaymentIntentNotFound(f"Payment {payment_id} not found")

    return {
        "payment_id": payment.id,
        "status": payment.status,
        "provider": payment.provider,
        "currency": payment.currency,
        "amount": str(payment.amount),
        "credits_awarded": payment.credits_awarded,
    }


async def get_payment_status(
    session: AsyncSession,
    *,
    payment_id: int,
    payment_repo: PaymentRepository,
) -> PaymentStatusResponse:
    """
    FASE 2: Obtiene el estado de un pago para polling del Frontend.
    
    Contrato estable:
    - is_final=False → FE debe seguir haciendo polling
    - is_final=True → estado definitivo
    - Nunca expone datos sensibles
    - retry_after_seconds sugiere cuánto esperar
    - status siempre es string lowercase
    """
    payment = await payment_repo.get(session, payment_id)
    if not payment:
        raise PaymentIntentNotFound(f"Payment {payment_id} not found")
    
    # Normalizar status a string (Enum.value si es Enum, else str)
    status_str = (
        payment.status.value 
        if hasattr(payment.status, 'value') 
        else str(payment.status)
    )
    
    # Determinar si el estado es final
    is_final = status_str in FINAL_STATUSES
    
    return PaymentStatusResponse(
        payment_id=payment.id,
        status=status_str,
        is_final=is_final,
        credits_awarded=payment.credits_awarded,
        webhook_verified_at=payment.webhook_verified_at,
        updated_at=payment.updated_at,
        retry_after_seconds=DEFAULT_RETRY_SECONDS,
    )


__all__ = [
    "get_payment_intent",
    "get_payment_status",
    "PaymentIntentNotFound",
]

# Fin del archivo backend/app/modules/payments/facades/payments/intents.py
