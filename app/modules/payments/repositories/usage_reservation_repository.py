
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/repositories/usage_reservation_repository.py

Repositorio para la tabla usage_reservations.

Responsabilidades:
- Idempotencia por operation_id
- Listado de reservas activas/pendientes por wallet
- Localizar reservas expiradas para liberarlas

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.modules.payments.enums import ReservationStatus
from app.modules.payments.models.usage_reservation_models import UsageReservation
from app.modules.payments.utils.datetime_helpers import utcnow


class UsageReservationRepository(BaseRepository[UsageReservation]):
    def __init__(self) -> None:
        super().__init__(UsageReservation)

    # -----------------------------------------------------------
    # Idempotencia: una reserva por operation_id
    # -----------------------------------------------------------
    async def get_by_operation_id(
        self,
        session: AsyncSession,
        operation_id: str,
    ) -> Optional[UsageReservation]:
        stmt = select(UsageReservation).where(
            UsageReservation.operation_id == operation_id
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    # -----------------------------------------------------------
    # Reservas activas/pendientes por wallet
    # -----------------------------------------------------------
    async def list_active_by_wallet(
        self,
        session: AsyncSession,
        wallet_id: int,
    ) -> Sequence[UsageReservation]:
        stmt = select(UsageReservation).where(
            and_(
                UsageReservation.wallet_id == wallet_id,
                UsageReservation.status.in_(
                    [ReservationStatus.PENDING, ReservationStatus.ACTIVE]
                ),
            )
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    # -----------------------------------------------------------
    # Reservas expiradas para liberar
    # -----------------------------------------------------------
    async def list_expired(
        self,
        session: AsyncSession,
        now: datetime | None = None,
    ) -> Sequence[UsageReservation]:
        """
        Obtiene reservas que ya expiraron y siguen en estado pendiente/activo.
        """
        if now is None:
            now = utcnow()

        stmt = select(UsageReservation).where(
            and_(
                UsageReservation.expires_at <= now,
                UsageReservation.status.in_(
                    [ReservationStatus.PENDING, ReservationStatus.ACTIVE]
                ),
            )
        )
        result = await session.execute(stmt)
        return result.scalars().all()

# Fin del archivo backend\app\modules\payments\repositories\usage_reservation_repository.py