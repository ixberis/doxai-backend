# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/credits/repositories.py

Repositorios para el sistema de créditos.

Autor: DoxAI
Fecha: 2025-12-30
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Wallet, CreditTransaction, UsageReservation
from .enums import CreditTxType, ReservationStatus

logger = logging.getLogger(__name__)


class WalletRepository:
    """Repositorio para operaciones CRUD de Wallet."""
    
    async def get_by_user_id(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> Optional[Wallet]:
        """
        Obtiene la wallet de un usuario.
        """
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_or_create(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> tuple[Wallet, bool]:
        """
        Obtiene o crea una wallet para el usuario.
        
        Usa SAVEPOINT para manejar concurrencia sin invalidar
        la transacción principal del request.
        
        Returns:
            Tuple (wallet, created: bool)
        """
        # Primero intentar obtener con lock
        wallet = await self.get_by_user_id(session, user_id, for_update=True)
        if wallet:
            return wallet, False
        
        # Usar SAVEPOINT para manejar IntegrityError sin romper transacción
        async with session.begin_nested():
            wallet = Wallet(
                user_id=user_id,
                balance=0,
                balance_reserved=0,
            )
            session.add(wallet)
            try:
                await session.flush()
                logger.info("Wallet created for user %s", user_id)
                return wallet, True
            except IntegrityError:
                # SAVEPOINT hace rollback automático, continuar
                pass
        
        # Concurrencia: otro proceso creó la wallet, obtenerla
        logger.debug("Wallet already exists for user %s (concurrent create)", user_id)
        wallet = await self.get_by_user_id(session, user_id, for_update=True)
        if wallet:
            return wallet, False
        
        # No debería llegar aquí
        raise RuntimeError(f"Failed to get or create wallet for user {user_id}")
    
    async def update_balance(
        self,
        session: AsyncSession,
        wallet: Wallet,
        delta: int,
        delta_reserved: int = 0,
    ) -> Wallet:
        """
        Actualiza el balance de una wallet.
        """
        wallet.balance += delta
        wallet.balance_reserved += delta_reserved
        wallet.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return wallet


class CreditTransactionRepository:
    """Repositorio para operaciones CRUD de CreditTransaction (ledger)."""
    
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        tx_type: CreditTxType,
        credits_delta: int,
        balance_after: int,
        description: Optional[str] = None,
        operation_code: Optional[str] = None,
        job_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        payment_id: Optional[int] = None,
        reservation_id: Optional[int] = None,
        tx_metadata: Optional[dict] = None,
    ) -> CreditTransaction:
        """
        Crea una transacción en el ledger de créditos.
        
        Validaciones:
        - credits_delta != 0
        """
        if credits_delta == 0:
            raise ValueError("credits_delta cannot be zero")
        
        tx = CreditTransaction(
            user_id=user_id,
            tx_type=tx_type if isinstance(tx_type, CreditTxType) else CreditTxType(tx_type),
            credits_delta=credits_delta,
            balance_after=balance_after,
            description=description,
            operation_code=operation_code,
            job_id=job_id,
            idempotency_key=idempotency_key,
            payment_id=payment_id,
            reservation_id=reservation_id,
            tx_metadata=tx_metadata or {},
        )
        session.add(tx)
        await session.flush()
        
        logger.debug(
            "CreditTransaction created: user=%s delta=%+d after=%d op=%s",
            user_id, credits_delta, balance_after, operation_code,
        )
        return tx
    
    async def get_by_idempotency_key(
        self,
        session: AsyncSession,
        user_id: int,
        idempotency_key: str,
    ) -> Optional[CreditTransaction]:
        """
        Busca una transacción por clave de idempotencia.
        """
        stmt = select(CreditTransaction).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.idempotency_key == idempotency_key,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_reservation_id(
        self,
        session: AsyncSession,
        reservation_id: int,
        tx_type: Optional[CreditTxType] = None,
    ) -> Optional[CreditTransaction]:
        """
        Busca una transacción por reservation_id.
        
        Útil para verificar idempotencia en consume_reservation.
        """
        stmt = select(CreditTransaction).where(
            CreditTransaction.reservation_id == reservation_id
        )
        if tx_type:
            stmt = stmt.where(
                CreditTransaction.tx_type == (
                    tx_type if isinstance(tx_type, CreditTxType) else CreditTxType(tx_type)
                )
            )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_balance(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> int:
        """
        Calcula el balance actual sumando el ledger.
        """
        stmt = select(func.coalesce(func.sum(CreditTransaction.credits_delta), 0)).where(
            CreditTransaction.user_id == user_id
        )
        result = await session.execute(stmt)
        return int(result.scalar_one())
    
    async def list_by_user(
        self,
        session: AsyncSession,
        user_id: int,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CreditTransaction]:
        """
        Lista transacciones de un usuario ordenadas por fecha descendente.
        """
        stmt = (
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class UsageReservationRepository:
    """Repositorio para operaciones CRUD de UsageReservation."""
    
    async def create(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        credits_reserved: int,
        operation_code: Optional[str] = None,
        job_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        reason: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        status: ReservationStatus = ReservationStatus.ACTIVE,
    ) -> UsageReservation:
        """
        Crea una reservación de créditos.
        """
        # Normalizar status a enum si viene como string
        status_enum = status if isinstance(status, ReservationStatus) else ReservationStatus(status)
        
        reservation = UsageReservation(
            user_id=user_id,
            credits_reserved=credits_reserved,
            credits_consumed=0,
            operation_code=operation_code,
            job_id=job_id,
            idempotency_key=idempotency_key,
            reason=reason,
            reservation_status=status_enum,
            reservation_expires_at=expires_at,
        )
        session.add(reservation)
        await session.flush()
        
        logger.debug(
            "UsageReservation created: id=%s user=%s credits=%d op=%s",
            reservation.id, user_id, credits_reserved, operation_code,
        )
        return reservation
    
    async def get_by_id(
        self,
        session: AsyncSession,
        reservation_id: int,
        *,
        for_update: bool = False,
    ) -> Optional[UsageReservation]:
        """
        Obtiene una reservación por ID.
        """
        stmt = select(UsageReservation).where(UsageReservation.id == reservation_id)
        if for_update:
            stmt = stmt.with_for_update()
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_operation_id(
        self,
        session: AsyncSession,
        operation_id: str,
        *,
        for_update: bool = False,
    ) -> Optional[UsageReservation]:
        """
        Obtiene una reservación por operation_code (operation_id).
        """
        stmt = select(UsageReservation).where(
            UsageReservation.operation_code == operation_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_status(
        self,
        session: AsyncSession,
        reservation: UsageReservation,
        new_status: ReservationStatus,
        *,
        credits_consumed: Optional[int] = None,
    ) -> UsageReservation:
        """
        Actualiza el estado de una reservación.
        """
        now = datetime.now(timezone.utc)
        
        # Normalizar a enum si viene como string
        status_enum = new_status if isinstance(new_status, ReservationStatus) else ReservationStatus(new_status)
        reservation.reservation_status = status_enum
        reservation.updated_at = now
        
        if credits_consumed is not None:
            reservation.credits_consumed = credits_consumed
        
        if new_status == ReservationStatus.CONSUMED:
            reservation.consumed_at = now
        elif new_status == ReservationStatus.EXPIRED:
            reservation.expired_at = now
        elif new_status == ReservationStatus.CANCELLED:
            reservation.released_at = now
        
        await session.flush()
        return reservation
    
    async def get_active_by_user(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> List[UsageReservation]:
        """
        Lista reservaciones activas de un usuario.
        """
        stmt = (
            select(UsageReservation)
            .where(
                UsageReservation.user_id == user_id,
                UsageReservation.reservation_status.in_([
                    ReservationStatus.PENDING,
                    ReservationStatus.ACTIVE,
                ]),
            )
            .order_by(UsageReservation.created_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


__all__ = [
    "WalletRepository",
    "CreditTransactionRepository",
    "UsageReservationRepository",
]
