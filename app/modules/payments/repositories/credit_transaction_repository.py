
# -*- coding: utf-8 -*-
"""
Repositorio del ledger de créditos.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.modules.payments.models.credit_transaction_models import CreditTransaction


class CreditTransactionRepository(BaseRepository[CreditTransaction]):
    def __init__(self):
        super().__init__(CreditTransaction)

    # -----------------------------------------------------------
    # Buscar por idempotency_key (para welcome_credits y otras operaciones)
    # -----------------------------------------------------------
    async def get_by_idempotency_key(
        self, session: AsyncSession, user_id: int, idempotency_key: str
    ) -> Optional[CreditTransaction]:
        """Busca transacción por user_id + idempotency_key (constraint único)."""
        stmt = select(CreditTransaction).where(
            and_(
                CreditTransaction.user_id == user_id,
                CreditTransaction.idempotency_key == idempotency_key,
            )
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    # -----------------------------------------------------------
    # Buscar por operation_code (legacy compat)
    # -----------------------------------------------------------
    async def get_by_operation_id(
        self, session: AsyncSession, operation_id: str
    ) -> Optional[CreditTransaction]:
        """Busca por operation_code (alias para compat)."""
        stmt = select(CreditTransaction).where(
            CreditTransaction.operation_code == operation_id
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    # -----------------------------------------------------------
    # Ledger por user_id
    # -----------------------------------------------------------
    async def list_by_user(
        self, session: AsyncSession, user_id: int
    ):
        stmt = select(CreditTransaction).where(
            CreditTransaction.user_id == user_id
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    # -----------------------------------------------------------
    # Suma de créditos (balance ledger) por user_id
    # -----------------------------------------------------------
    async def compute_balance(
        self, session: AsyncSession, user_id: int
    ) -> int:
        stmt = select(func.sum(CreditTransaction.credits_delta)).where(
            CreditTransaction.user_id == user_id
        )
        result = await session.execute(stmt)
        total = result.scalar()
        return total or 0
    
# Fin del archivo backend\app\modules\payments\repositories\credit_transaction_repository.py