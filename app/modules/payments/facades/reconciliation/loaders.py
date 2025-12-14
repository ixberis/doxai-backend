
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/reconciliation/loaders.py

Carga de datos internos para reconciliación.

Autor: Ixchel Beristáin
Fecha: 26/10/2025 (ajustado 20/11/2025)
"""

from __future__ import annotations

import logging
from typing import List, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.modules.payments.enums import PaymentProvider
from app.modules.payments.models.payment_models import Payment
from app.modules.payments.models.payment_event_models import PaymentEvent
from app.modules.payments.facades.webhooks.constants import (
    STRIPE_SUCCESS_EVENTS,
    PAYPAL_SUCCESS_EVENTS,
)

logger = logging.getLogger(__name__)


async def load_internal_payments(
    db: AsyncSession,
    provider: PaymentProvider,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Payment]:
    """
    Carga pagos internos del período y proveedor.
    """
    filters = [Payment.provider == provider]

    if start_date:
        filters.append(Payment.created_at >= start_date)
    if end_date:
        filters.append(Payment.created_at <= end_date)

    stmt = select(Payment).where(and_(*filters)).order_by(Payment.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def has_success_events(db: AsyncSession, payment_id: int) -> bool:
    """
    Verifica si un pago tiene eventos de éxito.
    SINGLE SOURCE OF TRUTH: Usa STRIPE_SUCCESS_EVENTS y PAYPAL_SUCCESS_EVENTS.
    """
    all_success_events = STRIPE_SUCCESS_EVENTS | PAYPAL_SUCCESS_EVENTS

    stmt = (
        select(PaymentEvent)
        .where(
            and_(
                PaymentEvent.payment_id == payment_id,
                PaymentEvent.event_type.in_(list(all_success_events)),
            )
        )
        .limit(1)
    )

    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


__all__ = [
    "load_internal_payments",
    "has_success_events",
]

# Fin del archivo backend/app/modules/payments/facades/reconciliation/loaders.py
