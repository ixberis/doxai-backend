
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/repositories/payment_repository.py

Repositorio para la tabla payments.

Responsabilidades:
- Búsqueda por intent del proveedor (Stripe/PayPal)
- Idempotencia por idempotency_key
- Listado por usuario y estado

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.repository import BaseRepository
from app.modules.payments.enums import PaymentStatus
from app.modules.payments.models.payment_models import Payment


class PaymentRepository(BaseRepository[Payment]):
    def __init__(self) -> None:
        super().__init__(Payment)

    # -----------------------------------------------------------
    # Búsquedas clave para idempotencia e integración
    # -----------------------------------------------------------
    async def get_by_payment_intent_id(
        self,
        session: AsyncSession,
        payment_intent_id: str,
    ) -> Optional[Payment]:
        """Obtiene un payment por el ID de intent/orden del proveedor."""
        stmt = select(Payment).where(Payment.provider_payment_id == payment_intent_id)
        result = await session.execute(stmt)
        return result.scalars().first()
    
    async def get_by_provider_payment_id(
        self,
        session: AsyncSession,
        provider: "PaymentProvider",
        provider_payment_id: str,
    ) -> Optional[Payment]:
        """Obtiene un payment por provider y provider_payment_id."""
        from app.modules.payments.enums import PaymentProvider
        
        stmt = select(Payment).where(
            Payment.provider == provider,
            Payment.provider_payment_id == provider_payment_id,
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def get_by_idempotency_key(
        self,
        session: AsyncSession,
        idempotency_key: str,
    ) -> Optional[Payment]:
        """Obtiene un payment por su clave idempotente interna."""
        stmt = select(Payment).where(Payment.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalars().first()

    # -----------------------------------------------------------
    # Listados por usuario / estado
    # -----------------------------------------------------------
    async def list_by_user(
        self,
        session: AsyncSession,
        user_id: str,
        status: PaymentStatus | None = None,
    ) -> Sequence[Payment]:
        """
        Lista pagos de un usuario, opcionalmente filtrando por estado.
        """
        stmt = select(Payment).where(Payment.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Payment.status == status)
        stmt = stmt.order_by(Payment.created_at.desc())
        result = await session.execute(stmt)
        return result.scalars().all()

# Fin del archivo backend\app\modules\payments\repositories\payment_repository.py