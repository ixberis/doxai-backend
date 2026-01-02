# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/services/checkout_service.py

Servicio para aplicar créditos tras checkout exitoso.

Autor: DoxAI
Fecha: 2025-12-29 (refactored 2025-12-30)
Actualizado: 2026-01-01 (completed_at idempotente)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import CheckoutIntent, CheckoutIntentStatus
from app.modules.billing.repository import CheckoutIntentRepository
from app.modules.billing.credits.services import WalletService

logger = logging.getLogger(__name__)


class CheckoutService:
    """
    Servicio para procesar checkouts completados.
    
    Maneja la transición de checkout_intent a completed
    y registra los créditos en el ledger real.
    """
    
    def __init__(
        self,
        intent_repo: Optional[CheckoutIntentRepository] = None,
        wallet_service: Optional[WalletService] = None,
    ):
        self.intent_repo = intent_repo or CheckoutIntentRepository()
        self.wallet_service = wallet_service or WalletService()
    
    async def apply_credits_for_intent(
        self,
        session: AsyncSession,
        intent_id: int,
        stripe_session_id: Optional[str] = None,
    ) -> tuple[CheckoutIntent, bool]:
        """
        Marca un checkout intent como completado y acredita al ledger.
        
        Idempotente: si ya está completed, retorna sin cambios.
        completed_at se setea una sola vez (primera transición a completed).
        """
        # 1) Obtener intent
        intent = await self.intent_repo.get_by_id(session, intent_id)
        if intent is None:
            raise ValueError(f"Checkout intent {intent_id} not found")
        
        # 2) Idempotencia: si ya está completed, no hacer nada
        if intent.status == CheckoutIntentStatus.COMPLETED.value:
            logger.info("Intent %s already completed (idempotent)", intent_id)
            return intent, False
        
        # 3) Actualizar estado del intent a completed
        intent.status = CheckoutIntentStatus.COMPLETED.value
        
        # 4) Setear completed_at UNA SOLA VEZ (idempotente)
        #    Solo se setea si es None (primera transición a completed)
        if intent.completed_at is None:
            intent.completed_at = datetime.now(timezone.utc)
        
        if stripe_session_id and not intent.provider_session_id:
            intent.provider_session_id = stripe_session_id
        
        # 5) Acreditar al ledger real
        await self.wallet_service.add_credits(
            session,
            intent.user_id,
            intent.credits_amount,
            operation_code="CHECKOUT",
            description=f"Checkout {intent.package_id}: {intent.credits_amount} créditos",
            idempotency_key=f"checkout_{intent_id}",
            tx_metadata={
                "intent_id": intent_id,
                "package_id": intent.package_id,
                "provider": intent.provider,
            },
        )
        
        await session.flush()
        
        logger.info(
            "Checkout completed: intent=%s, user=%s, credits=%d, completed_at=%s",
            intent_id, intent.user_id, intent.credits_amount, intent.completed_at,
        )
        
        return intent, True
    
    async def get_user_credit_balance(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> int:
        """
        Calcula el balance de créditos de un usuario.
        
        Usa el ledger real (wallet) como fuente de verdad.
        """
        return await self.wallet_service.get_balance(session, user_id)


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
