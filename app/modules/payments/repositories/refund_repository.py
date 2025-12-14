
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/repositories/refund_repository.py

Repositorio para la tabla refunds.

Responsabilidades:
- Idempotencia por provider_refund_id
- Listado por payment
- Listado por estado

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.modules.payments.enums import RefundStatus
from app.modules.payments.models.refund_models import Refund


class RefundRepository(BaseRepository[Refund]):
    def __init__(self) -> None:
        super().__init__(Refund)

    # -----------------------------------------------------------
    # Idempotencia: no registrar dos veces el mismo refund
    # -----------------------------------------------------------
    async def get_by_provider_refund_id(
        self,
        session: AsyncSession,
        provider_refund_id: str,
    ) -> Optional[Refund]:
        stmt = select(Refund).where(Refund.provider_refund_id == provider_refund_id)
        result = await session.execute(stmt)
        return result.scalars().first()

    # -----------------------------------------------------------
    # Listados por payment / estado
    # -----------------------------------------------------------
    async def list_by_payment(
        self,
        session: AsyncSession,
        payment_id: int,
    ) -> Sequence[Refund]:
        stmt = select(Refund).where(Refund.payment_id == payment_id)
        stmt = stmt.order_by(Refund.created_at.asc())
        result = await session.execute(stmt)
        return result.scalars().all()

    async def list_by_status(
        self,
        session: AsyncSession,
        status: RefundStatus,
    ) -> Sequence[Refund]:
        stmt = select(Refund).where(Refund.status == status)
        result = await session.execute(stmt)
        return result.scalars().all()

# Fin del archivo backend\app\modules\payments\repositories\refund_repository.py