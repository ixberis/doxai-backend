
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/credit_service.py

Servicio para operaciones atómicas sobre el ledger de créditos
(credit_transactions).

Implementa la regla central del sistema:
- credits_delta > 0  = ingreso de créditos
- credits_delta < 0  = consumo de créditos
- operation_id = idempotencia garantizada

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import CreditTxType
from app.modules.payments.models.credit_transaction_models import CreditTransaction
from app.modules.payments.repositories.credit_transaction_repository import (
    CreditTransactionRepository,
)

logger = logging.getLogger(__name__)


class CreditService:
    """Operaciones atómicas del ledger (créditos)."""

    def __init__(
        self,
        db_or_repo: AsyncSession | CreditTransactionRepository,
    ) -> None:
        """
        Acepta AsyncSession (para ActivationService) o CreditTransactionRepository.
        """
        if isinstance(db_or_repo, CreditTransactionRepository):
            self._db: Optional[AsyncSession] = None
            self.credit_repo = db_or_repo
        else:
            # AsyncSession u otro objeto (incluyendo mocks en tests)
            self._db = db_or_repo
            self.credit_repo = CreditTransactionRepository()

    # ---------------------------------------------------------
    # Welcome credits (idempotente) - usado por ActivationService
    # ---------------------------------------------------------
    async def ensure_welcome_credits(
        self,
        user_id: int,
        welcome_credits: int = 5,
    ) -> bool:
        """
        Asigna créditos de bienvenida de forma idempotente.
        
        Usa user_id + idempotency_key para garantizar idempotencia vía constraint DB.
        Utiliza savepoint (begin_nested) para no afectar la transacción exterior.
        
        Returns:
            True si se crearon los créditos (primera vez)
            False si ya existían (idempotente)
            
        Raises:
            ValueError: si no hay session disponible
        """
        from sqlalchemy.exc import IntegrityError
        
        if self._db is None:
            raise ValueError("CreditService requires AsyncSession for ensure_welcome_credits")
        
        session = self._db
        idempotency_key = "welcome_credits"
        
        # Fast-path: verificar idempotencia antes de intentar insertar
        existing = await self.credit_repo.get_by_idempotency_key(
            session, user_id, idempotency_key
        )
        if existing:
            logger.info("Welcome credits already assigned for user_id=%s (idempotent)", user_id)
            return False
        
        # Calcular balance actual para balance_after
        current_balance = await self.credit_repo.compute_balance(session, user_id)
        new_balance = current_balance + welcome_credits
        
        # Crear transacción de crédito usando savepoint para no afectar tx exterior
        tx = CreditTransaction(
            user_id=user_id,
            tx_type=CreditTxType.CREDIT,
            credits_delta=welcome_credits,
            balance_after=new_balance,
            idempotency_key=idempotency_key,
            operation_code="welcome_credits",
            description="Créditos de bienvenida",
            metadata_json={"reason": "welcome_credits"},
        )
        
        try:
            # Usar savepoint (begin_nested) para aislar posible IntegrityError
            async with session.begin_nested():
                session.add(tx)
                await session.flush()
            
            logger.info(
                "Assigned %d welcome credits to user_id=%s (balance_after=%s)",
                welcome_credits, user_id, new_balance
            )
            return True
        except IntegrityError:
            # Constraint violation = ya existe (race condition)
            # El savepoint se hace rollback automáticamente, no afecta tx exterior
            logger.info("Welcome credits already exist for user_id=%s (IntegrityError, idempotent)", user_id)
            return False

    # ---------------------------------------------------------
    # Alta idempotente de movimientos (API original)
    # ---------------------------------------------------------
    async def apply_credit(
        self,
        session: AsyncSession,
        wallet_id: int,
        amount: int,
        operation_id: str,
        metadata: dict | None = None,
    ):
        """
        credit → credits_delta positivo.
        """
        if amount <= 0:
            raise ValueError("Amount must be > 0 for apply_credit")

        # idempotencia
        existing = await self.credit_repo.get_by_operation_id(session, operation_id)
        if existing:
            return existing

        return await self.credit_repo.create(
            session,
            wallet_id=wallet_id,
            tx_type=CreditTxType.CREDIT,
            credits_delta=amount,
            operation_id=operation_id,
            metadata_json=metadata or {},
        )

    async def apply_debit(
        self,
        session: AsyncSession,
        wallet_id: int,
        amount: int,
        operation_id: str,
        metadata: dict | None = None,
    ):
        """
        debit → credits_delta negativo.
        Se valida saldo disponible antes de permitir el débito.
        """
        if amount <= 0:
            raise ValueError("Amount must be > 0 for apply_debit")

        # idempotencia
        existing = await self.credit_repo.get_by_operation_id(session, operation_id)
        if existing:
            return existing

        # saldo insuficiente ⇒ error
        balance = await self.credit_repo.compute_balance(session, wallet_id)
        if balance < amount:
            raise ValueError(
                f"Insufficient credits (balance={balance}, debit={amount})"
            )

        return await self.credit_repo.create(
            session,
            wallet_id=wallet_id,
            tx_type=CreditTxType.DEBIT,
            credits_delta=-amount,
            operation_id=operation_id,
            metadata_json=metadata or {},
        )

    # ---------------------------------------------------------
    # Revertir crédito (para refunds)
    # ---------------------------------------------------------
    async def reverse_credit(
        self,
        session: AsyncSession,
        wallet_id: int,
        amount: int,
        operation_id: str,
        metadata: dict | None = None,
    ):
        """
        Reversión (refund):
        - créditos_delta negativo (retira créditos previamente otorgados).
        """
        if amount <= 0:
            raise ValueError("Amount must be > 0 for reverse_credit")

        existing = await self.credit_repo.get_by_operation_id(session, operation_id)
        if existing:
            return existing

        return await self.credit_repo.create(
            session,
            wallet_id=wallet_id,
            tx_type=CreditTxType.DEBIT,
            credits_delta=-amount,
            operation_id=operation_id,
            metadata_json=metadata or {},
        )

# Fin del archivo backend/app/modules/payments/services/credit_service.py