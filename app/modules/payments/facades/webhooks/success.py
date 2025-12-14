# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/webhooks/success.py

Flujos de alto nivel para procesamiento de webhooks:
- éxito de pago (con validación anti-fraude)
- fallo de pago
- refund

FASE 1: Agrega validación de amount/currency y correlación user_id.

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import PaymentStatus
from app.modules.payments.services.payment_service import PaymentService
from app.modules.payments.services.refund_service import RefundService
from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.repositories.refund_repository import RefundRepository
from app.modules.payments.facades.webhooks.normalize import NormalizedWebhook

logger = logging.getLogger(__name__)


class AmountMismatchError(ValueError):
    """El monto del webhook no coincide con el Payment interno."""
    pass


class CurrencyMismatchError(ValueError):
    """La moneda del webhook no coincide con el Payment interno."""
    pass


class UserMismatchError(ValueError):
    """El usuario del webhook no coincide con el Payment interno."""
    pass


async def handle_payment_success(
    *,
    session: AsyncSession,
    payment_service: PaymentService,
    payment_repo: PaymentRepository,
    payment_id: int,
    webhook_amount_cents: Optional[int] = None,
    webhook_currency: Optional[str] = None,
    webhook_user_id: Optional[int] = None,
) -> "Payment":
    """
    Marca un payment como succeeded y acredita créditos.
    
    FASE 1: Valida que amount/currency/user coincidan con el Payment interno.
    
    Args:
        session: Sesión de DB
        payment_service: Servicio de pagos
        payment_repo: Repositorio de pagos
        payment_id: ID del payment interno
        webhook_amount_cents: Monto reportado por el webhook (para validación)
        webhook_currency: Moneda reportada por el webhook (para validación)
        webhook_user_id: User ID del webhook si está disponible (para validación)
    
    Returns:
        Payment actualizado
    
    Raises:
        ValueError: Si el payment no existe
        AmountMismatchError: Si el monto no coincide
        CurrencyMismatchError: Si la moneda no coincide
        UserMismatchError: Si el usuario no coincide
    """
    from app.modules.payments.models.payment_models import Payment
    
    payment = await payment_repo.get(session, payment_id)
    if not payment:
        raise ValueError(f"Payment {payment_id} not found")
    
    # VALIDACIÓN ANTI-FRAUDE: Monto
    if webhook_amount_cents is not None:
        if payment.amount_cents != webhook_amount_cents:
            logger.error(
                f"FRAUDE POTENCIAL: Amount mismatch para Payment {payment_id}. "
                f"Esperado: {payment.amount_cents} cents, Webhook: {webhook_amount_cents} cents"
            )
            raise AmountMismatchError(
                f"Amount mismatch: expected {payment.amount_cents}, got {webhook_amount_cents}"
            )
    
    # VALIDACIÓN ANTI-FRAUDE: Moneda
    if webhook_currency is not None:
        payment_currency = payment.currency.value.upper() if hasattr(payment.currency, 'value') else str(payment.currency).upper()
        webhook_currency_upper = webhook_currency.upper()
        
        if payment_currency != webhook_currency_upper:
            logger.error(
                f"FRAUDE POTENCIAL: Currency mismatch para Payment {payment_id}. "
                f"Esperado: {payment_currency}, Webhook: {webhook_currency_upper}"
            )
            raise CurrencyMismatchError(
                f"Currency mismatch: expected {payment_currency}, got {webhook_currency_upper}"
            )
    
    # VALIDACIÓN ANTI-FRAUDE: Usuario
    if webhook_user_id is not None:
        if payment.user_id != webhook_user_id:
            logger.error(
                f"FRAUDE POTENCIAL: User mismatch para Payment {payment_id}. "
                f"Esperado: {payment.user_id}, Webhook: {webhook_user_id}"
            )
            raise UserMismatchError(
                f"User mismatch: expected {payment.user_id}, got {webhook_user_id}"
            )
    
    # Marcar webhook_verified_at
    if hasattr(payment, 'webhook_verified_at'):
        payment.webhook_verified_at = datetime.now(timezone.utc)
    
    return await payment_service.apply_success(session, payment)


async def handle_payment_failure(
    *,
    session: AsyncSession,
    payment_service: PaymentService,
    payment_repo: PaymentRepository,
    payment_id: int,
    reason: str | None,
):
    """Marca un payment con estado FAILED."""
    payment = await payment_repo.get(session, payment_id)
    if not payment:
        raise ValueError(f"Payment {payment_id} not found")

    return await payment_service.mark_failed(session, payment, reason)


async def handle_payment_refund(
    *,
    session: AsyncSession,
    refund_service: RefundService,
    refund_repo: RefundRepository,
    payment_repo: PaymentRepository,
    normalized: NormalizedWebhook,
):
    """
    Aplica refund utilizando refund_service.apply_success.
    """
    payment = await payment_repo.get(session, normalized.payment_id)
    if not payment:
        raise ValueError(f"Payment {normalized.payment_id} not found")

    # Usar refund_amount_cents del webhook o el monto del refund en el raw
    refund_amount_cents = normalized.refund_amount_cents
    if refund_amount_cents is None:
        refund_amount_cents = normalized.raw.get("refund_amount", 0)
        if isinstance(refund_amount_cents, str):
            refund_amount_cents = int(Decimal(refund_amount_cents) * 100)
    
    # Convertir a Decimal para el servicio
    refund_amount = Decimal(refund_amount_cents) / 100

    refund = await refund_service.create_refund(
        session,
        payment=payment,
        amount=refund_amount,
        credits_reversed=payment.credits_awarded,
        currency=payment.currency,
        provider_refund_id=normalized.provider_refund_id or normalized.event_id,
    )

    wallet_id = await _find_wallet_id_for_payment(session, payment_repo, payment)
    return await refund_service.apply_success(
        session, refund=refund, wallet_id=wallet_id
    )


async def _find_wallet_id_for_payment(
    session: AsyncSession,
    payment_repo: PaymentRepository,
    payment,
) -> int:
    """Helper: obtiene wallet_id desde payment.user_id."""
    from app.modules.payments.repositories.wallet_repository import WalletRepository

    wallet_repo = WalletRepository()
    wallet = await wallet_repo.get_by_user_id(session, payment.user_id)
    if not wallet:
        raise ValueError(f"Wallet not found for user {payment.user_id}")
    return wallet.id


__all__ = [
    "handle_payment_success",
    "handle_payment_failure",
    "handle_payment_refund",
    "AmountMismatchError",
    "CurrencyMismatchError",
    "UserMismatchError",
]
