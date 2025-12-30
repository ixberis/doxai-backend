# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/credits/services.py

Servicios para el sistema de créditos.

Provee lógica de negocio para:
- CreditService: transacciones en el ledger y consulta de balance
- WalletService: gestión de wallets de usuario
- ReservationService: reserva/consumo/liberación de créditos para jobs

Autor: DoxAI
Fecha: 2025-12-30
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

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
    user_id: int


class WalletService:
    """
    Servicio para gestión de wallets de usuario.
    """
    
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
        user_id: int,
    ) -> Wallet:
        """
        Obtiene o crea una wallet para el usuario.
        
        Maneja concurrencia vía IntegrityError.
        """
        wallet, _ = await self.wallet_repo.get_or_create(session, user_id)
        return wallet
    
    async def get_balance(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> int:
        """
        Obtiene el balance de créditos de un usuario.
        """
        wallet = await self.wallet_repo.get_by_user_id(session, user_id)
        if wallet:
            return wallet.balance
        return 0
    
    async def get_available(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> int:
        """
        Obtiene los créditos disponibles (balance - reserved).
        """
        wallet = await self.wallet_repo.get_by_user_id(session, user_id)
        if wallet:
            return wallet.available
        return 0
    
    async def add_credits(
        self,
        session: AsyncSession,
        user_id: int,
        credits: int,
        *,
        operation_code: str,
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        payment_id: Optional[int] = None,
        tx_metadata: Optional[dict] = None,
    ) -> CreditTransaction:
        """
        Añade créditos al usuario (abono).
        
        Actualiza wallet + crea transacción en ledger.
        Idempotente vía idempotency_key.
        """
        if credits <= 0:
            raise ValueError("credits must be positive")
        
        # Idempotencia
        if idempotency_key:
            existing = await self.tx_repo.get_by_idempotency_key(
                session, user_id, idempotency_key
            )
            if existing:
                logger.info(
                    "Idempotent add_credits: already exists for user=%s key=%s",
                    user_id, idempotency_key,
                )
                return existing
        
        # Obtener/crear wallet y actualizar balance
        wallet = await self.get_or_create_wallet(session, user_id)
        await self.wallet_repo.update_balance(session, wallet, delta=credits)
        
        # Crear transacción en ledger
        tx = await self.tx_repo.create(
            session,
            user_id=user_id,
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
            "Credits added: user=%s credits=%+d balance=%d op=%s",
            user_id, credits, wallet.balance, operation_code,
        )
        return tx
    
    async def deduct_credits(
        self,
        session: AsyncSession,
        user_id: int,
        credits: int,
        *,
        operation_code: str,
        description: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        reservation_id: Optional[int] = None,
        job_id: Optional[str] = None,
        tx_metadata: Optional[dict] = None,
    ) -> CreditTransaction:
        """
        Deduce créditos del usuario (cargo).
        
        Raises:
            ValueError: Si no hay suficientes créditos disponibles
        """
        if credits <= 0:
            raise ValueError("credits must be positive")
        
        # Idempotencia
        if idempotency_key:
            existing = await self.tx_repo.get_by_idempotency_key(
                session, user_id, idempotency_key
            )
            if existing:
                logger.info(
                    "Idempotent deduct_credits: already exists for user=%s key=%s",
                    user_id, idempotency_key,
                )
                return existing
        
        # Verificar balance disponible
        wallet = await self.wallet_repo.get_by_user_id(session, user_id, for_update=True)
        if not wallet or wallet.available < credits:
            raise ValueError(
                f"Insufficient credits: available={wallet.available if wallet else 0}, required={credits}"
            )
        
        # Actualizar wallet (decrementar balance)
        await self.wallet_repo.update_balance(session, wallet, delta=-credits)
        
        # Crear transacción en ledger
        tx = await self.tx_repo.create(
            session,
            user_id=user_id,
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
            "Credits deducted: user=%s credits=%d balance=%d op=%s",
            user_id, credits, wallet.balance, operation_code,
        )
        return tx


class CreditService:
    """
    Servicio para gestión de créditos de usuario.
    
    Combina operaciones de wallet con ledger para:
    - Asignar créditos de bienvenida
    - Consultar balance
    - Consultar historial de transacciones
    """
    
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
        user_id: int,
        welcome_credits: int = 5,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """
        Asegura que un usuario tenga créditos de bienvenida.
        
        Idempotente: si ya tiene créditos de SIGNUP_BONUS, no crea más.
        """
        db = session or self.session
        if not db:
            logger.warning("CreditService.ensure_welcome_credits: no session provided")
            return False
        
        idempotency_key = f"welcome_credits_{user_id}"
        
        # Verificar si ya tiene welcome credits
        existing = await self.tx_repo.get_by_idempotency_key(
            db, user_id, idempotency_key
        )
        if existing:
            logger.debug("Welcome credits already exist for user %s", user_id)
            return False
        
        # Crear transacción de welcome credits
        await self.wallet_service.add_credits(
            db,
            user_id,
            welcome_credits,
            operation_code="SIGNUP_BONUS",
            description=f"Créditos de bienvenida ({welcome_credits})",
            idempotency_key=idempotency_key,
            tx_metadata={"type": "welcome_credits"},
        )
        
        logger.info(
            "Welcome credits assigned: user=%s credits=%d",
            user_id, welcome_credits,
        )
        return True
    
    async def get_balance(
        self,
        user_id: int,
        session: Optional[AsyncSession] = None,
    ) -> int:
        """
        Obtiene el balance de créditos de un usuario.
        """
        db = session or self.session
        if not db:
            return 0
        return await self.wallet_service.get_balance(db, user_id)
    
    async def get_available(
        self,
        user_id: int,
        session: Optional[AsyncSession] = None,
    ) -> int:
        """
        Obtiene los créditos disponibles de un usuario.
        """
        db = session or self.session
        if not db:
            return 0
        return await self.wallet_service.get_available(db, user_id)


class ReservationService:
    """
    Servicio para reserva, consumo y liberación de créditos.
    
    Usado por pipelines RAG y otras operaciones que necesitan
    apartar créditos antes de ejecutar.
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
    
    async def create_reservation(
        self,
        session: AsyncSession,
        user_id: int,
        credits: int,
        operation_id: str,
        ttl_minutes: int = 30,
    ) -> ReservationResult:
        """
        Crea una reservación de créditos.
        
        Aparta créditos en wallet.balance_reserved para que no puedan
        usarse en otras operaciones.
        
        Args:
            session: Sesión de base de datos
            user_id: ID del usuario
            credits: Cantidad de créditos a reservar
            operation_id: Identificador único de la operación
            ttl_minutes: Tiempo de vida de la reservación
            
        Returns:
            ReservationResult con los datos de la reservación
            
        Raises:
            ValueError: Si no hay suficientes créditos disponibles
        """
        # Obtener/crear wallet y verificar disponibilidad
        wallet, _ = await self.wallet_repo.get_or_create(session, user_id)
        
        if wallet.available < credits:
            raise ValueError(
                f"Insufficient credits for reservation: available={wallet.available}, required={credits}"
            )
        
        # Calcular expiración
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        
        # Crear reservación
        reservation = await self.reservation_repo.create(
            session,
            user_id=user_id,
            credits_reserved=credits,
            operation_code=operation_id,
            expires_at=expires_at,
            status=ReservationStatus.ACTIVE,
        )
        
        # Apartar créditos en wallet
        await self.wallet_repo.update_balance(
            session, wallet, delta=0, delta_reserved=credits
        )
        
        logger.info(
            "Reservation created: id=%s user=%s credits=%d op=%s expires=%s",
            reservation.id, user_id, credits, operation_id, expires_at,
        )
        
        return ReservationResult(
            reservation_id=reservation.id,
            wallet_id=wallet.id,
            credits=credits,
            operation_id=operation_id,
            user_id=user_id,
        )
    
    async def consume_reservation(
        self,
        session: AsyncSession,
        operation_id: str,
        ledger_operation_id: Optional[str] = None,
        actual_credits: Optional[int] = None,
    ) -> bool:
        """
        Consume una reservación y registra el débito en el ledger.
        
        Idempotente:
        - Si la reservación ya está consumed, retorna True sin duplicar
        - Si ya existe una tx en ledger para esta reservación, no duplica
        
        Args:
            session: Sesión de base de datos
            operation_id: ID de la operación (operation_code de la reservación)
            ledger_operation_id: ID para la transacción del ledger
            actual_credits: Créditos realmente usados (default: todos los reservados)
            
        Returns:
            True si se consumió exitosamente o ya estaba consumida
        """
        # Buscar reservación por operation_id
        reservation = await self.reservation_repo.get_by_operation_id(
            session, operation_id, for_update=True
        )
        
        if not reservation:
            logger.warning("Reservation not found for operation: %s", operation_id)
            return False
        
        # Idempotencia: si ya está consumed, retornar OK
        if reservation.reservation_status == ReservationStatus.CONSUMED.value:
            logger.debug("Reservation %s already consumed (idempotent)", reservation.id)
            return True
        
        if reservation.reservation_status not in [
            ReservationStatus.ACTIVE.value,
            ReservationStatus.PENDING.value,
        ]:
            logger.warning(
                "Reservation %s not consumable: status=%s",
                reservation.id, reservation.reservation_status,
            )
            return False
        
        # Idempotencia: verificar si ya existe tx en ledger
        existing_tx = await self.tx_repo.get_by_reservation_id(
            session, reservation.id, CreditTxType.DEBIT
        )
        if existing_tx:
            logger.debug(
                "Ledger tx already exists for reservation %s (idempotent)",
                reservation.id,
            )
            # Actualizar estado si no está actualizado
            if reservation.reservation_status != ReservationStatus.CONSUMED.value:
                await self.reservation_repo.update_status(
                    session, reservation, ReservationStatus.CONSUMED,
                    credits_consumed=abs(existing_tx.credits_delta),
                )
            return True
        
        # Determinar créditos a consumir
        credits_to_consume = actual_credits or reservation.credits_reserved
        
        # Obtener wallet
        wallet = await self.wallet_repo.get_by_user_id(
            session, reservation.user_id, for_update=True
        )
        if not wallet:
            logger.error("Wallet not found for user %s", reservation.user_id)
            return False
        
        # Actualizar wallet:
        # - Decrementar balance por credits_to_consume
        # - Decrementar balance_reserved por credits_reserved (todo lo apartado)
        await self.wallet_repo.update_balance(
            session,
            wallet,
            delta=-credits_to_consume,
            delta_reserved=-reservation.credits_reserved,
        )
        
        # Registrar en ledger usando repo directamente (no vía wallet_service)
        await self.tx_repo.create(
            session,
            user_id=reservation.user_id,
            tx_type=CreditTxType.DEBIT,
            credits_delta=-credits_to_consume,
            balance_after=wallet.balance,
            description=f"Consumo de reservación {reservation.id}",
            operation_code=ledger_operation_id or operation_id,
            reservation_id=reservation.id,
            idempotency_key=f"consume_{reservation.id}",
        )
        
        # Actualizar estado de reservación
        await self.reservation_repo.update_status(
            session,
            reservation,
            ReservationStatus.CONSUMED,
            credits_consumed=credits_to_consume,
        )
        
        logger.info(
            "Reservation consumed: id=%s user=%s consumed=%d",
            reservation.id, reservation.user_id, credits_to_consume,
        )
        
        return True
    
    async def release_reservation(
        self,
        session: AsyncSession,
        reservation_id: int,
    ) -> bool:
        """
        Libera una reservación sin consumir.
        
        Devuelve los créditos apartados al disponible.
        Idempotente si ya está cancelled/consumed/expired.
        """
        reservation = await self.reservation_repo.get_by_id(
            session, reservation_id, for_update=True
        )
        
        if not reservation:
            logger.warning("Reservation not found: %s", reservation_id)
            return False
        
        if reservation.reservation_status not in [
            ReservationStatus.ACTIVE.value,
            ReservationStatus.PENDING.value,
        ]:
            logger.debug(
                "Reservation %s already processed: status=%s",
                reservation_id, reservation.reservation_status,
            )
            return True  # Ya procesada, idempotente
        
        # Obtener wallet y liberar créditos apartados
        wallet = await self.wallet_repo.get_by_user_id(
            session, reservation.user_id, for_update=True
        )
        if wallet:
            await self.wallet_repo.update_balance(
                session,
                wallet,
                delta=0,
                delta_reserved=-reservation.credits_reserved,
            )
        
        # Marcar como cancelada
        await self.reservation_repo.update_status(
            session,
            reservation,
            ReservationStatus.CANCELLED,
        )
        
        logger.info(
            "Reservation released: id=%s user=%s credits=%d",
            reservation_id, reservation.user_id, reservation.credits_reserved,
        )
        
        return True


__all__ = [
    "ReservationResult",
    "WalletService",
    "CreditService",
    "ReservationService",
]
