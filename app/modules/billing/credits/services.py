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
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .models import Wallet, CreditTransaction, UsageReservation
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
    ) -> Wallet:
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
    ) -> CreditTransaction:
        if credits <= 0:
            raise ValueError("credits must be positive")

        if idempotency_key:
            existing = await self.tx_repo.get_by_idempotency_key(session, auth_user_id, idempotency_key)
            if existing:
                logger.info(
                    "Idempotent add_credits: already exists for auth_user_id=%s key=%s",
                    str(auth_user_id)[:8] + "...", idempotency_key,
                )
                return existing

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
        return tx

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
    ) -> CreditTransaction:
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
        Asegura que un usuario tenga créditos de bienvenida (SSOT auth_user_id).

        Idempotente: si ya tiene créditos de SIGNUP_BONUS, no crea más.

        IMPORTANT:
        - Si ocurre error de DB, hacemos rollback best-effort para NO dejar
          la transacción del request en estado abortado (evita 500 en activación).
        """
        db = session or self.session
        if not db:
            logger.warning("CreditService.ensure_welcome_credits: no session provided")
            return False

        idempotency_key = f"welcome_credits:{auth_user_id}"

        try:
            existing = await self.tx_repo.get_by_idempotency_key(db, auth_user_id, idempotency_key)
            if existing:
                logger.debug("Welcome credits already exist for auth_user_id %s", str(auth_user_id)[:8] + "...")
                return False

            await self.wallet_service.add_credits(
                db,
                auth_user_id,
                welcome_credits,
                operation_code="SIGNUP_BONUS",
                description=f"Créditos de bienvenida ({welcome_credits})",
                idempotency_key=idempotency_key,
                tx_metadata={"type": "welcome_credits"},
            )

            logger.info(
                "Welcome credits assigned: auth_user_id=%s credits=%d",
                str(auth_user_id)[:8] + "...", welcome_credits,
            )
            return True

        except Exception as e:
            # Best-effort rollback to prevent InFailedSQLTransactionError downstream
            try:
                await db.rollback()
            except Exception:
                pass
            logger.error(
                "CreditService.ensure_welcome_credits failed for auth_user_id=%s: %s",
                str(auth_user_id)[:8] + "...",
                str(e),
                exc_info=True,
            )
            return False

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


# ReservationService: dejo sin cambios funcionales aquí porque requiere refactor mayor.
# Si tus tablas en DB 2.0 ya migraron a auth_user_id, lo ajustamos después (Fase Billing).
class ReservationService:
    def __init__(
        self,
        reservation_repo: Optional[UsageReservationRepository] = None,
        wallet_repo: Optional[WalletRepository] = None,
        tx_repo: Optional[CreditTransactionRepository] = None,
    ):
        self.reservation_repo = reservation_repo or UsageReservationRepository()
        self.wallet_repo = wallet_repo or WalletRepository()
        self.tx_repo = tx_repo or CreditTransactionRepository()

    # (Mantén el resto como está en tu repo actual; lo ajustamos cuando toques RAG billing)


__all__ = [
    "ReservationResult",
    "WalletService",
    "CreditService",
    "ReservationService",
]

