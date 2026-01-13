# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/credits/services.py

Servicios para el sistema de créditos.

Autor: DoxAI
Fecha: 2025-12-30
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .enums import CreditTxType, ReservationStatus
from .repositories import (
    WalletRepository,
    CreditTransactionRepository,
    UsageReservationRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class ReservationResult:
    """Resultado de crear una reservación."""
    reservation_id: int
    wallet_id: int
    credits: int
    operation_id: str
    auth_user_id: UUID


class WalletService:
    def __init__(
        self,
        wallet_repo: Optional[WalletRepository] = None,
        tx_repo: Optional[CreditTransactionRepository] = None,
    ):
        self.wallet_repo = wallet_repo or WalletRepository()
        self.tx_repo = tx_repo or CreditTransactionRepository()

    async def get_or_create_wallet(
        self,
        session: AsyncSession,
        auth_user_id: UUID,
    ):
        wallet, _ = await self.wallet_repo.get_or_create(session, auth_user_id)
        return wallet

    async def get_balance(
        self,
        session: AsyncSession,
        auth_user_id: UUID,
    ) -> int:
        wallet = await self.wallet_repo.get_by_auth_user_id(session, auth_user_id)
        if wallet:
            return wallet.balance
        return 0

    async def get_available(
        self,
        session: AsyncSession,
        auth_user_id: UUID,
    ) -> int:
        wallet = await self.wallet_repo.get_by_auth_user_id(session, auth_user_id)
        if wallet:
            return wallet.available
        return 0

    async def add_credits(
        self,
        session: AsyncSession,
        auth_user_id: UUID,
        credits: int,
        *,
        operation_code: str,
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        payment_id: Optional[int] = None,
        tx_metadata: Optional[dict] = None,
    ) -> tuple["CreditTransaction", bool]:
        """
        Añade créditos al wallet del usuario.
        
        Returns:
            Tuple de (CreditTransaction, created: bool)
            - created=True: nueva transacción creada
            - created=False: transacción existente retornada (idempotencia)
        """
        if credits <= 0:
            raise ValueError("credits must be positive")

        if idempotency_key:
            existing = await self.tx_repo.get_by_idempotency_key(session, auth_user_id, idempotency_key)
            if existing:
                logger.info(
                    "Idempotent add_credits: already exists for auth_user_id=%s key=%s",
                    str(auth_user_id)[:8] + "...", idempotency_key,
                )
                return existing, False  # Existing, not created

        wallet = await self.get_or_create_wallet(session, auth_user_id)
        await self.wallet_repo.update_balance(session, wallet, delta=credits)

        tx = await self.tx_repo.create(
            session,
            auth_user_id=auth_user_id,
            tx_type=CreditTxType.CREDIT,
            credits_delta=credits,
            balance_after=wallet.balance,
            description=description,
            operation_code=operation_code,
            idempotency_key=idempotency_key,
            payment_id=payment_id,
            tx_metadata=tx_metadata,
        )

        logger.info(
            "Credits added: auth_user_id=%s credits=%+d balance=%d op=%s",
            str(auth_user_id)[:8] + "...", credits, wallet.balance, operation_code,
        )
        return tx, True  # New transaction created

    async def deduct_credits(
        self,
        session: AsyncSession,
        auth_user_id: UUID,
        credits: int,
        *,
        operation_code: str,
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        reservation_id: Optional[int] = None,
        job_id: Optional[str] = None,
        tx_metadata: Optional[dict] = None,
    ):
        if credits <= 0:
            raise ValueError("credits must be positive")

        if idempotency_key:
            existing = await self.tx_repo.get_by_idempotency_key(session, auth_user_id, idempotency_key)
            if existing:
                logger.info(
                    "Idempotent deduct_credits: already exists for auth_user_id=%s key=%s",
                    str(auth_user_id)[:8] + "...", idempotency_key,
                )
                return existing

        wallet = await self.wallet_repo.get_by_auth_user_id(session, auth_user_id, for_update=True)
        if not wallet or wallet.available < credits:
            raise ValueError(
                f"Insufficient credits: available={wallet.available if wallet else 0}, required={credits}"
            )

        await self.wallet_repo.update_balance(session, wallet, delta=-credits)

        tx = await self.tx_repo.create(
            session,
            auth_user_id=auth_user_id,
            tx_type=CreditTxType.DEBIT,
            credits_delta=-credits,
            balance_after=wallet.balance,
            description=description,
            operation_code=operation_code,
            idempotency_key=idempotency_key,
            reservation_id=reservation_id,
            job_id=job_id,
            tx_metadata=tx_metadata,
        )

        logger.info(
            "Credits deducted: auth_user_id=%s credits=%d balance=%d op=%s",
            str(auth_user_id)[:8] + "...", credits, wallet.balance, operation_code,
        )
        return tx


class CreditService:
    def __init__(
        self,
        session: Optional[AsyncSession] = None,
        wallet_service: Optional[WalletService] = None,
        tx_repo: Optional[CreditTransactionRepository] = None,
    ):
        self.session = session
        self.wallet_service = wallet_service or WalletService()
        self.tx_repo = tx_repo or CreditTransactionRepository()

    async def ensure_welcome_credits(
        self,
        *,
        auth_user_id: UUID,
        welcome_credits: int = 5,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """
        Asigna créditos de bienvenida exactamente una vez (idempotente).
        
        La idempotencia se delega completamente a WalletService.add_credits,
        que verifica el idempotency_key internamente para evitar duplicados.
        
        IMPORTANTE: Este método usa flush() internamente, NO commit().
        El caller (ActivationService) es responsable del commit final.
        Esto permite transacción atómica: activación + wallet + créditos.
        
        Returns:
            True si se asignaron créditos nuevos.
            False si ya existían (idempotencia).
            
        Raises:
            Exception: Propaga errores al caller para manejo transaccional.
        """
        db = session or self.session
        if not db:
            logger.warning("CreditService.ensure_welcome_credits: no session provided")
            return False

        idempotency_key = f"welcome_credits:{auth_user_id}"

        # add_credits uses flush() internally, not commit()
        # This allows the caller to control the transaction boundary
        tx, is_new = await self.wallet_service.add_credits(
            db,
            auth_user_id,
            welcome_credits,
            operation_code="SIGNUP_BONUS",
            description=f"Créditos de bienvenida ({welcome_credits})",
            idempotency_key=idempotency_key,
            tx_metadata={"type": "welcome_credits"},
        )

        if is_new:
            logger.info(
                "Welcome credits assigned: auth_user_id=%s credits=%d",
                str(auth_user_id)[:8] + "...", welcome_credits,
            )
        else:
            logger.info(
                "Welcome credits idempotent (already exist): auth_user_id=%s",
                str(auth_user_id)[:8] + "...",
            )
        return is_new

    async def get_balance(
        self,
        auth_user_id: UUID,
        session: Optional[AsyncSession] = None,
    ) -> int:
        db = session or self.session
        if not db:
            return 0
        return await self.wallet_service.get_balance(db, auth_user_id)

    async def get_available(
        self,
        auth_user_id: UUID,
        session: Optional[AsyncSession] = None,
    ) -> int:
        db = session or self.session
        if not db:
            return 0
        return await self.wallet_service.get_available(db, auth_user_id)


class ReservationService:
    """
    Servicio para consumir reservaciones de créditos (RAG billing).

    Nota:
    - SSOT es auth_user_id.
    - Idempotencia:
        * Si la reservación ya está CONSUMED → True
        * Si ya existe tx ledger asociada a reservation_id → no duplica y marca CONSUMED
    """

    def __init__(
        self,
        reservation_repo: Optional[UsageReservationRepository] = None,
        wallet_repo: Optional[WalletRepository] = None,
        tx_repo: Optional[CreditTransactionRepository] = None,
    ):
        self.reservation_repo = reservation_repo or UsageReservationRepository()
        self.wallet_repo = wallet_repo or WalletRepository()
        self.tx_repo = tx_repo or CreditTransactionRepository()

    async def consume_reservation(self, session: AsyncSession, operation_id: str) -> bool:
        """
        Consume una reservación (deja ledger DEBIT y actualiza wallet/reservation).

        Args:
            session: AsyncSession
            operation_id: identificador de operación (se guarda en reservation.operation_code)

        Returns:
            True si se consumió o ya estaba consumida (idempotente).
        """
        reservation = await self.reservation_repo.get_by_operation_id(session, operation_id, for_update=True)
        if not reservation:
            # Comportamiento conservador: no-op idempotente
            logger.warning("consume_reservation: reservation not found for operation_id=%s", operation_id)
            return False

        if reservation.reservation_status == ReservationStatus.CONSUMED:
            return True

        # Idempotencia por ledger: si ya existe tx (por reservation_id) no duplicar
        existing_tx = await self.tx_repo.get_by_reservation_id(session, reservation.id, tx_type=CreditTxType.DEBIT)
        if existing_tx:
            await self.reservation_repo.update_status(
                session,
                reservation,
                ReservationStatus.CONSUMED,
                credits_consumed=reservation.credits_reserved,
            )
            return True

        credits = int(reservation.credits_reserved or 0)
        if credits <= 0:
            logger.warning("consume_reservation: invalid credits_reserved=%s for reservation_id=%s", credits, reservation.id)
            await self.reservation_repo.update_status(
                session,
                reservation,
                ReservationStatus.CONSUMED,
                credits_consumed=0,
            )
            return True

        # Wallet lock
        wallet = await self.wallet_repo.get_by_auth_user_id(session, reservation.auth_user_id, for_update=True)
        if not wallet:
            raise ValueError("Wallet not found for reservation auth_user_id")

        # Al consumir: reducir balance y reserved en la misma magnitud
        await self.wallet_repo.update_balance(session, wallet, delta=-credits, delta_reserved=-credits)

        # Ledger debit asociado a reservation_id (no duplica por uq)
        await self.tx_repo.create(
            session,
            auth_user_id=reservation.auth_user_id,
            tx_type=CreditTxType.DEBIT,
            credits_delta=-credits,
            balance_after=wallet.balance,
            operation_code=reservation.operation_code,
            reservation_id=reservation.id,
            tx_metadata={"type": "reservation_consume", "operation_id": operation_id},
        )

        await self.reservation_repo.update_status(
            session,
            reservation,
            ReservationStatus.CONSUMED,
            credits_consumed=credits,
        )

        return True

    async def create_reservation(
        self,
        session: AsyncSession,
        auth_user_id: UUID,
        credits: int,
        *,
        operation_id: str,
        operation_code: Optional[str] = None,
        job_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        reason: Optional[str] = None,
        expires_at: Optional[object] = None,  # datetime | None (evitar typing extra)
    ) -> ReservationResult:
        """
        Crea una reservación de créditos (SSOT auth_user_id).

        Idempotencia mínima:
        - Si ya existe reservación con operation_id (mapeado a operation_code),
          regresa la existente sin duplicar.

        Nota:
        - Reservar NO descuenta balance total; solo incrementa balance_reserved.
        """
        if credits <= 0:
            raise ValueError("credits must be positive")

        # Idempotencia por operation_id (en repo se busca por operation_code)
        existing = await self.reservation_repo.get_by_operation_id(session, operation_id, for_update=True)
        if existing:
            return ReservationResult(
                reservation_id=existing.id,
                wallet_id=0,  # no siempre tenemos wallet loaded aquí; se puede llenar si lo necesitas
                credits=int(existing.credits_reserved or 0),
                operation_id=operation_id,
                auth_user_id=existing.auth_user_id,
            )

        # Wallet (lock) + validación de fondos disponibles
        wallet = await self.wallet_repo.get_by_auth_user_id(session, auth_user_id, for_update=True)
        if not wallet:
            wallet, _ = await self.wallet_repo.get_or_create(session, auth_user_id)

        if wallet.available < credits:
            raise ValueError(
                f"Insufficient credits: available={wallet.available}, required={credits}"
            )

        # Reservar: subir reserved, mantener balance
        await self.wallet_repo.update_balance(session, wallet, delta=0, delta_reserved=credits)

        reservation = await self.reservation_repo.create(
            session,
            auth_user_id=auth_user_id,
            credits_reserved=credits,
            operation_code=operation_code or operation_id,
            job_id=job_id,
            idempotency_key=idempotency_key,
            reason=reason,
            expires_at=expires_at,  # repo lo guarda como reservation_expires_at
            status=ReservationStatus.ACTIVE,
        )

        return ReservationResult(
            reservation_id=reservation.id,
            wallet_id=wallet.id,
            credits=credits,
            operation_id=operation_id,
            auth_user_id=auth_user_id,
        )


__all__ = [
    "ReservationResult",
    "WalletService",
    "CreditService",
    "ReservationService",
]

# Fin del archivo 
