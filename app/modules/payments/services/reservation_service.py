
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/reservation_service.py

Servicio para manejar reservas de créditos (usage_reservations).

Flujos cubiertos:
- Crear reserva (idempotente por operation_id)
- Consumir reserva (genera débito en el ledger)
- Liberar/cancelar reserva (sin tocar el ledger)
- Expirar reservas vencidas

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import ReservationStatus
from app.modules.payments.repositories.usage_reservation_repository import (
    UsageReservationRepository,
)
from app.modules.payments.repositories.wallet_repository import WalletRepository
from app.modules.payments.services.wallet_service import WalletService
from app.modules.payments.services.credit_service import CreditService
from app.modules.payments.utils.datetime_helpers import utcnow

if TYPE_CHECKING:  # solo para type checkers, evita ciclos en runtime
    from app.modules.payments.models.usage_reservation_models import UsageReservation
    from app.modules.payments.models.wallet_models import Wallet


class ReservationService:
    """
    Orquestador de reservas de créditos.

    Importante:
    - La reserva en sí misma NO mueve créditos en el ledger.
    - El ledger se afecta cuando la reserva se consume (debit).
    - balance_reserved de la wallet se mantiene consistente
      con las reservas activas/pendientes.
    """

    def __init__(
        self,
        reservation_repo: UsageReservationRepository,
        wallet_repo: WalletRepository,
        wallet_service: WalletService,
        credit_service: CreditService,
    ) -> None:
        self.reservation_repo = reservation_repo
        self.wallet_repo = wallet_repo
        self.wallet_service = wallet_service
        self.credit_service = credit_service

    # ------------------------------------------------------------------ #
    # Helpers internos
    # ------------------------------------------------------------------ #
    async def _get_wallet_or_error(
        self, session: AsyncSession, wallet_id: int
    ) -> "Wallet":
        wallet = await self.wallet_repo.get(session, wallet_id)
        if wallet is None:
            raise ValueError(f"Wallet {wallet_id} not found")
        return wallet

    # ------------------------------------------------------------------ #
    # Crear reserva
    # ------------------------------------------------------------------ #
    async def create_reservation(
        self,
        session: AsyncSession,
        wallet_id: int,
        credits: int,
        operation_id: str,
        ttl_minutes: int = 30,
    ) -> "UsageReservation":
        """
        Crea una reserva de créditos idempotente por operation_id.

        Pasos:
        - Si ya existe reserva con ese operation_id → la regresa (idempotente).
        - Verifica créditos suficientes.
        - Crea reserva en estado PENDING.
        - Incrementa balance_reserved de la wallet.
        """
        if credits <= 0:
            raise ValueError("Reservation credits must be > 0")

        existing = await self.reservation_repo.get_by_operation_id(
            session, operation_id
        )
        if existing:
            return existing

        wallet = await self._get_wallet_or_error(session, wallet_id)

        # Verificar créditos suficientes
        await self.wallet_service.ensure_sufficient_credits(
            session, wallet, required=credits
        )

        expires_at = utcnow() + timedelta(minutes=ttl_minutes)

        reservation = await self.reservation_repo.create(
            session,
            wallet_id=wallet_id,
            status=ReservationStatus.PENDING,
            credits_reserved=credits,
            operation_id=operation_id,
            expires_at=expires_at,
        )

        # Actualizar balance_reserved local de la wallet
        await self.wallet_service.reserve_credits(session, wallet, credits)

        return reservation

    # ------------------------------------------------------------------ #
    # Consumir reserva
    # ------------------------------------------------------------------ #
    async def consume_reservation(
        self,
        session: AsyncSession,
        operation_id: str,
        ledger_operation_id: Optional[str] = None,
    ) -> "UsageReservation":
        """
        Consume una reserva existente (genera un débito en el ledger).

        - Solo permite consumir reservas PENDING/ACTIVE no expiradas.
        - Aplica debit al ledger vía CreditService.
        - Cambia el estado de la reserva a CONSUMED.
        - Reduce balance_reserved de la wallet.

        ledger_operation_id permite usar un operation_id distinto
        para el movimiento contable; si no se especifica se reutiliza
        el operation_id de la reserva.
        """
        reservation = await self.reservation_repo.get_by_operation_id(
            session, operation_id
        )
        if reservation is None:
            raise ValueError(f"Reservation with operation_id={operation_id} not found")

        if reservation.status not in (
            ReservationStatus.PENDING,
            ReservationStatus.ACTIVE,
        ):
            # Idempotencia / no hacer nada si ya se consumió/canceló
            return reservation

        now = utcnow()
        if reservation.expires_at <= now:
            # Si ya expiró, la marcamos como EXPIRED y liberamos
            await self._expire_single(session, reservation)
            raise ValueError("Reservation is expired and cannot be consumed")

        # Débito de créditos (ledger)
        op_id_ledger = ledger_operation_id or f"{operation_id}:consume"
        await self.credit_service.apply_debit(
            session,
            wallet_id=reservation.wallet_id,
            amount=reservation.credits_reserved,
            operation_id=op_id_ledger,
            metadata={"reservation_operation_id": operation_id},
        )

        # Actualizar reserva y wallet
        reservation.status = ReservationStatus.CONSUMED
        wallet = await self._get_wallet_or_error(session, reservation.wallet_id)
        await self.wallet_service.release_reserved(
            session, wallet, reservation.credits_reserved
        )

        await session.flush()
        return reservation

    # ------------------------------------------------------------------ #
    # Cancelar/liberar reserva sin consumo
    # ------------------------------------------------------------------ #
    async def cancel_reservation(
        self,
        session: AsyncSession,
        operation_id: str,
    ) -> "UsageReservation":
        """
        Cancela una reserva:
        - Solo si está PENDING/ACTIVE.
        - No toca el ledger.
        - Libera balance_reserved.
        """
        reservation = await self.reservation_repo.get_by_operation_id(
            session, operation_id
        )
        if reservation is None:
            raise ValueError(f"Reservation with operation_id={operation_id} not found")

        if reservation.status not in (
            ReservationStatus.PENDING,
            ReservationStatus.ACTIVE,
        ):
            # Ya fue procesada; consideramos la operación idempotente
            return reservation

        reservation.status = ReservationStatus.CANCELLED

        wallet = await self._get_wallet_or_error(session, reservation.wallet_id)
        await self.wallet_service.release_reserved(
            session, wallet, reservation.credits_reserved
        )

        await session.flush()
        return reservation

    # ------------------------------------------------------------------ #
    # Expiración de reservas
    # ------------------------------------------------------------------ #
    async def _expire_single(
        self,
        session: AsyncSession,
        reservation: "UsageReservation",
    ) -> None:
        """Marca una reserva como EXPIRED y libera balance_reserved."""
        if reservation.status not in (
            ReservationStatus.PENDING,
            ReservationStatus.ACTIVE,
        ):
            return

        reservation.status = ReservationStatus.EXPIRED
        wallet = await self._get_wallet_or_error(session, reservation.wallet_id)
        await self.wallet_service.release_reserved(
            session, wallet, reservation.credits_reserved
        )

        await session.flush()

    async def expire_reservations(
        self,
        session: AsyncSession,
        now: Optional[datetime] = None,
    ) -> int:
        """
        Marca como EXPIRED todas las reservas vencidas y libera créditos.

        Returns:
            int: número de reservas expiradas.
        """
        now = now or utcnow()

        expired = await self.reservation_repo.list_expired(session, now=now)
        for reservation in expired:
            await self._expire_single(session, reservation)

        return len(expired)

# Fin del archivo backend\app\modules\payments\services\reservation_service.py