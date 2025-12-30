# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/services/checkout_service.py

Servicio para aplicar créditos tras checkout exitoso.

Maneja la lógica de negocio para:
- Actualizar estado de checkout_intent a completed
- Acreditar créditos al ledger (credit_transactions)
- Idempotencia vía checkout_intent_id

Autor: DoxAI
Fecha: 2025-12-29
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import CheckoutIntent, CheckoutIntentStatus
from app.modules.billing.repository import CheckoutIntentRepository
from app.modules.payments.enums import CreditTxType
from app.modules.payments.models.credit_transaction_models import CreditTransaction
from app.modules.payments.repositories.credit_transaction_repository import (
    CreditTransactionRepository,
)

logger = logging.getLogger(__name__)


class CheckoutService:
    """
    Servicio para procesar checkouts completados.
    
    Maneja la transición de checkout_intent a completed
    y la acreditación de créditos al ledger.
    """
    
    def __init__(
        self,
        intent_repo: Optional[CheckoutIntentRepository] = None,
        credit_repo: Optional[CreditTransactionRepository] = None,
    ):
        self.intent_repo = intent_repo or CheckoutIntentRepository()
        self.credit_repo = credit_repo or CreditTransactionRepository()
    
    async def apply_credits_for_intent(
        self,
        session: AsyncSession,
        intent_id: int,
        stripe_session_id: Optional[str] = None,
    ) -> tuple[CheckoutIntent, bool]:
        """
        Aplica créditos para un checkout intent completado.
        
        Idempotente: si ya se aplicaron los créditos, retorna el intent
        sin duplicar la transacción.
        
        Args:
            session: Sesión de base de datos
            intent_id: ID del checkout intent
            stripe_session_id: ID de sesión Stripe (para metadata)
            
        Returns:
            Tuple de (CheckoutIntent, credits_applied: bool)
            - credits_applied=True si se aplicaron créditos por primera vez
            - credits_applied=False si ya estaban aplicados (idempotente)
            
        Raises:
            ValueError: Si el intent no existe
        """
        # 1) Obtener intent
        intent = await self.intent_repo.get_by_id(session, intent_id)
        if intent is None:
            raise ValueError(f"Checkout intent {intent_id} not found")
        
        # 2) Idempotencia: si ya está completed, verificar créditos
        if intent.status == CheckoutIntentStatus.COMPLETED.value:
            logger.info(
                "Intent %s already completed, checking credits idempotency",
                intent_id,
            )
            # Verificar si ya existe la transacción
            idempotency_key = f"checkout_intent_{intent_id}"
            existing_tx = await self.credit_repo.get_by_idempotency_key(
                session, intent.user_id, idempotency_key
            )
            if existing_tx:
                logger.info("Credits already applied for intent %s", intent_id)
                return intent, False
        
        # 3) Aplicar créditos al ledger
        idempotency_key = f"checkout_intent_{intent_id}"
        
        # Verificar idempotencia antes de insertar
        existing_tx = await self.credit_repo.get_by_idempotency_key(
            session, intent.user_id, idempotency_key
        )
        if existing_tx:
            logger.info(
                "Credits already exist for intent %s (idempotent)",
                intent_id,
            )
            # Marcar como completed si no lo estaba
            if intent.status != CheckoutIntentStatus.COMPLETED.value:
                intent.status = CheckoutIntentStatus.COMPLETED.value
                await session.flush()
            return intent, False
        
        # 4) Calcular balance actual
        current_balance = await self.credit_repo.compute_balance(
            session, intent.user_id
        )
        new_balance = current_balance + intent.credits_amount
        
        # 5) Crear transacción de crédito
        tx = CreditTransaction(
            user_id=intent.user_id,
            tx_type=CreditTxType.CREDIT,
            credits_delta=intent.credits_amount,
            balance_after=new_balance,
            idempotency_key=idempotency_key,
            operation_code=f"purchase_{intent.package_id}",
            description=f"Compra de créditos: {intent.package_id}",
            metadata_json={
                "checkout_intent_id": intent_id,
                "package_id": intent.package_id,
                "price_cents": intent.price_cents,
                "currency": intent.currency,
                "stripe_session_id": stripe_session_id,
            },
        )
        session.add(tx)
        
        # 6) Actualizar estado del intent
        intent.status = CheckoutIntentStatus.COMPLETED.value
        
        await session.flush()
        
        logger.info(
            "Applied %d credits for intent %s (user=%s, balance=%d)",
            intent.credits_amount, intent_id, intent.user_id, new_balance,
        )
        
        return intent, True


async def apply_checkout_credits(
    session: AsyncSession,
    intent_id: int,
    stripe_session_id: Optional[str] = None,
) -> tuple[CheckoutIntent, bool]:
    """
    Función helper para aplicar créditos sin instanciar servicio.
    
    Wrapper conveniente sobre CheckoutService.apply_credits_for_intent().
    """
    service = CheckoutService()
    return await service.apply_credits_for_intent(
        session, intent_id, stripe_session_id
    )


__all__ = [
    "CheckoutService",
    "apply_checkout_credits",
]
