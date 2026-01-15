# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/services/finalize_service.py

Servicio canónico para finalizar checkout_intents completados.

Pipeline de finalización:
1. Valida intent (existe, pertenece a usuario, status=completed)
2. Crea registro en payments (SSOT de ingresos) - idempotente
3. Crea movimiento en credit_transactions (ledger) - idempotente
4. Actualiza wallet balance si aplica

IMPORTANTE: Este servicio es la ÚNICA forma canónica de materializar
un checkout completado en el sistema de ingresos.

Autor: DoxAI
Fecha: 2026-01-14
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.modules.billing.models import CheckoutIntent, CheckoutIntentStatus
from app.modules.billing.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    CurrencyEnum,
)
from app.modules.billing.credits.services import WalletService

logger = logging.getLogger(__name__)


@dataclass
class FinalizeResult:
    """Resultado de la finalización de un checkout."""
    intent_id: int
    payment_id: int
    auth_user_id: UUID
    credits_granted: int
    currency: str
    amount_cents: int
    idempotency_key: str
    result: Literal["created", "already_finalized"]


class BillingFinalizeService:
    """
    Servicio canónico para finalizar checkout_intents.
    
    Garantías:
    - Idempotencia: llamar N veces produce exactamente 1 payment + 1 credit_transaction
    - Atomicidad: todo o nada (rollback si falla cualquier paso)
    - SSOT: usa auth_user_id para ownership
    """
    
    def __init__(
        self,
        wallet_service: Optional[WalletService] = None,
    ):
        self.wallet_service = wallet_service or WalletService()
    
    async def finalize_checkout_intent(
        self,
        session: AsyncSession,
        intent_id: int,
    ) -> FinalizeResult:
        """
        Finaliza un checkout intent completado.
        
        Pipeline:
        1. Valida que el intent existe y está en status=completed
        2. Crea registro en payments (UPSERT idempotente)
        3. Crea movimiento en credit_transactions (via WalletService)
        
        Args:
            session: AsyncSession de SQLAlchemy
            intent_id: ID del checkout_intent a finalizar
            
        Returns:
            FinalizeResult con detalles de la operación
            
        Raises:
            ValueError: Si el intent no existe o no está completed
        """
        # 1) Obtener intent
        stmt = select(CheckoutIntent).where(CheckoutIntent.id == intent_id)
        result = await session.execute(stmt)
        intent = result.scalar_one_or_none()
        
        if intent is None:
            raise ValueError(f"Checkout intent {intent_id} not found")
        
        if intent.status != CheckoutIntentStatus.COMPLETED.value:
            raise ValueError(
                f"Checkout intent {intent_id} not completed (status={intent.status})"
            )
        
        # 2) Construir idempotency_key para payment
        payment_idem_key = f"checkout_intent_{intent_id}"
        
        # 3) Verificar si ya existe payment (idempotencia)
        existing_payment_stmt = select(Payment).where(
            Payment.auth_user_id == intent.auth_user_id,
            Payment.idempotency_key == payment_idem_key,
        )
        existing_result = await session.execute(existing_payment_stmt)
        existing_payment = existing_result.scalar_one_or_none()
        
        if existing_payment:
            logger.info(
                "checkout_intent_finalized intent_id=%d payment_id=%d "
                "auth_user_id=%s credits_granted=%d currency=%s "
                "amount_cents=%d idempotency_key=%s result=already_finalized",
                intent_id,
                existing_payment.id,
                str(intent.auth_user_id)[:8] + "...",
                intent.credits_amount,
                intent.currency,
                intent.price_cents,
                payment_idem_key,
            )
            return FinalizeResult(
                intent_id=intent_id,
                payment_id=existing_payment.id,
                auth_user_id=intent.auth_user_id,
                credits_granted=intent.credits_amount,
                currency=intent.currency,
                amount_cents=intent.price_cents,
                idempotency_key=payment_idem_key,
                result="already_finalized",
            )
        
        # 4) Validar datos del intent
        if not intent.credits_amount or intent.credits_amount <= 0:
            logger.warning(
                "finalize_checkout_intent: intent %d has invalid credits_amount=%s",
                intent_id,
                intent.credits_amount,
            )
        
        # 5) Determinar provider
        provider = self._resolve_provider(intent.provider)
        currency = self._resolve_currency(intent.currency)
        
        # 6) Crear Payment
        now = datetime.now(timezone.utc)
        payment = Payment(
            auth_user_id=intent.auth_user_id,
            provider=provider,
            status=PaymentStatus.SUCCEEDED,
            amount_cents=intent.price_cents,
            currency=currency,
            provider_payment_id=intent.provider_session_id,
            idempotency_key=payment_idem_key,
            credits_purchased=intent.credits_amount,
            captured=True,
            payment_metadata={
                "source": "checkout_intent",
                "intent_id": intent_id,
                "package_id": intent.package_id,
            },
            paid_at=intent.completed_at or now,
            succeeded_at=intent.completed_at or now,
        )
        session.add(payment)
        await session.flush()  # Obtener payment.id
        
        # 7) Crear credit_transaction via WalletService (idempotente)
        # Patrón canónico: checkout_credit_{id} para evitar colisiones
        credit_idem_key = f"checkout_credit_{intent_id}"
        await self.wallet_service.add_credits(
            session,
            intent.auth_user_id,
            intent.credits_amount,
            operation_code="CHECKOUT",
            description=f"Checkout {intent.package_id}: {intent.credits_amount} créditos",
            idempotency_key=credit_idem_key,
            payment_id=payment.id,
            tx_metadata={
                "intent_id": intent_id,
                "package_id": intent.package_id,
                "provider": provider.value,
                "payment_id": payment.id,
            },
        )
        
        logger.info(
            "checkout_intent_finalized intent_id=%d payment_id=%d "
            "auth_user_id=%s credits_granted=%d currency=%s "
            "amount_cents=%d idempotency_key=%s result=created",
            intent_id,
            payment.id,
            str(intent.auth_user_id)[:8] + "...",
            intent.credits_amount,
            intent.currency,
            intent.price_cents,
            payment_idem_key,
        )
        
        return FinalizeResult(
            intent_id=intent_id,
            payment_id=payment.id,
            auth_user_id=intent.auth_user_id,
            credits_granted=intent.credits_amount,
            currency=intent.currency,
            amount_cents=intent.price_cents,
            idempotency_key=payment_idem_key,
            result="created",
        )
    
    async def backfill_completed_intents(
        self,
        session: AsyncSession,
    ) -> list[FinalizeResult]:
        """
        Backfill: finaliza todos los checkout_intents completados sin payment.
        
        Idempotente: ejecutar múltiples veces no duplica datos.
        
        Returns:
            Lista de FinalizeResult para cada intent procesado
        """
        # Buscar intents completed que NO tienen payment asociado
        stmt = select(CheckoutIntent).where(
            CheckoutIntent.status == CheckoutIntentStatus.COMPLETED.value,
        )
        result = await session.execute(stmt)
        intents = result.scalars().all()
        
        results = []
        for intent in intents:
            try:
                finalize_result = await self.finalize_checkout_intent(
                    session,
                    intent.id,
                )
                results.append(finalize_result)
            except Exception as e:
                logger.error(
                    "backfill_completed_intents: failed for intent %d: %s",
                    intent.id,
                    str(e),
                )
                continue
        
        logger.info(
            "backfill_completed_intents: processed %d intents, "
            "created=%d already_finalized=%d",
            len(results),
            sum(1 for r in results if r.result == "created"),
            sum(1 for r in results if r.result == "already_finalized"),
        )
        
        return results
    
    def _resolve_provider(self, provider_str: Optional[str]) -> PaymentProvider:
        """Resuelve el provider string a enum."""
        if provider_str:
            provider_lower = provider_str.lower()
            if provider_lower == "paypal":
                return PaymentProvider.PAYPAL
        # Default a stripe (más común)
        return PaymentProvider.STRIPE
    
    def _resolve_currency(self, currency_str: str) -> CurrencyEnum:
        """Resuelve el currency string a enum."""
        currency_lower = currency_str.lower() if currency_str else "mxn"
        if currency_lower == "usd":
            return CurrencyEnum.USD
        return CurrencyEnum.MXN


# Función helper conveniente
async def finalize_checkout_intent(
    session: AsyncSession,
    intent_id: int,
) -> FinalizeResult:
    """
    Función helper para finalizar un checkout intent.
    
    Wrapper conveniente sobre BillingFinalizeService.finalize_checkout_intent().
    """
    service = BillingFinalizeService()
    return await service.finalize_checkout_intent(session, intent_id)


__all__ = [
    "BillingFinalizeService",
    "FinalizeResult",
    "finalize_checkout_intent",
]
