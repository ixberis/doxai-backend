
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/repositories/payment_event_repository.py

Repositorio para la tabla payment_events.

Responsabilidades:
- Idempotencia de eventos webhook (provider_event_id)
- Listado por payment

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.modules.payments.models.payment_event_models import PaymentEvent


class PaymentEventRepository(BaseRepository[PaymentEvent]):
    def __init__(self) -> None:
        super().__init__(PaymentEvent)

    # -----------------------------------------------------------
    # Idempotencia: no procesar dos veces el mismo evento
    # -----------------------------------------------------------
    async def get_by_provider_event_id(
        self,
        session: AsyncSession,
        provider_event_id: str,
    ) -> Optional[PaymentEvent]:
        stmt = select(PaymentEvent).where(
            PaymentEvent.provider_event_id == provider_event_id
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    # -----------------------------------------------------------
    # Eventos por payment
    # -----------------------------------------------------------
    async def list_by_payment(
        self,
        session: AsyncSession,
        payment_id: int,
    ) -> Sequence[PaymentEvent]:
        stmt = select(PaymentEvent).where(PaymentEvent.payment_id == payment_id)
        stmt = stmt.order_by(PaymentEvent.created_at.asc())
        result = await session.execute(stmt)
        return result.scalars().all()

# Fin del archivo backend\app\modules\payments\repositories\payment_event_repository.py