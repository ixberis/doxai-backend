# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/webhooks/stripe_handler.py

Handler de webhooks Stripe para billing (checkout de créditos).

Procesa eventos:
- checkout.session.completed: Aplica créditos al usuario + envía email
- checkout.session.expired: Marca intent como expirado

Autor: DoxAI
Fecha: 2025-12-29
Actualizado: 2026-01-12 - SSOT: auth_user_id UUID
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING, TypeAlias
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config.settings_payments import get_payments_settings
from app.modules.billing.services.finalize_service import (
    BillingFinalizeService,
    FinalizeResult,
)
from app.modules.billing.repository import CheckoutIntentRepository
from app.modules.billing.models import CheckoutIntent, CheckoutIntentStatus

# Import condicional de stripe para permitir tests sin el módulo
try:
    import stripe as stripe_sdk
    STRIPE_AVAILABLE = True
except ImportError:
    stripe_sdk = None  # type: ignore[assignment]
    STRIPE_AVAILABLE = False

# Type alias para evitar warnings de Pylance cuando stripe_sdk=None
if TYPE_CHECKING:
    import stripe as stripe_types
    StripeEvent: TypeAlias = stripe_types.Event
else:
    StripeEvent: TypeAlias = Any

logger = logging.getLogger(__name__)


def verify_stripe_webhook_signature(
    payload: bytes,
    sig_header: str,
    webhook_secret: Optional[str] = None,
) -> StripeEvent:
    """
    Verifica la firma de un webhook de Stripe.
    """
    if not STRIPE_AVAILABLE or stripe_sdk is None:
        raise RuntimeError("stripe SDK not installed")
    
    settings = get_payments_settings()
    secret = webhook_secret or settings.stripe_webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET")
    
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
    
    event = stripe_sdk.Webhook.construct_event(payload, sig_header, secret)
    return event


async def _send_purchase_email_best_effort(
    session: AsyncSession,
    intent_id: int,
    auth_user_id: UUID,
    payment_id: Optional[int] = None,
) -> Dict[str, bool]:
    """
    Envía email de confirmación de compra y notificación al admin (best-effort).
    
    SSOT: Uses auth_user_id (UUID) for user lookup.
    
    NOTA: No hace commit, el caller es responsable.
    Si payment_id es None, intenta resolver por idempotency_key canónico.
    Si no existe payment, envía notificación admin con payment_id="N/A".
    
    Returns:
        Dict con customer_email_sent y admin_notify_sent
    """
    result = {"customer_email_sent": False, "admin_notify_sent": False}
    
    try:
        from app.modules.billing.services.invoice_service import get_or_create_invoice
        from app.modules.billing.services.purchase_email_service import send_purchase_confirmation_email
        from app.modules.billing.services.admin_notification_service import send_admin_purchase_notification
        from app.modules.auth.models import AppUser
        from app.modules.billing.models.payment import Payment
        
        # Obtener intent primero
        repo = CheckoutIntentRepository()
        intent = await repo.get_by_id(session, intent_id)
        if not intent:
            logger.warning("Intent not found for email: intent=%s", intent_id)
            return result
        
        # SSOT: Obtener usuario por auth_user_id
        user_result = await session.execute(
            select(AppUser).where(AppUser.auth_user_id == auth_user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user or not user.user_email:
            logger.warning("User or email not found for purchase email: auth_user_id=%s", str(auth_user_id)[:8])
            return result
        
        # Crear o recuperar invoice (idempotente)
        invoice = await get_or_create_invoice(
            session=session,
            intent=intent,
            user_email=user.user_email,
            user_name=user.user_full_name,
        )
        logger.info("Invoice ready for email: invoice_id=%s intent=%s", invoice.id, intent_id)
        
        # Enviar email al cliente (idempotente)
        result["customer_email_sent"] = await send_purchase_confirmation_email(
            session=session,
            invoice=invoice,
            intent=intent,
            user_email=user.user_email,
            user_name=user.user_full_name,
        )
        
        # Resolver payment_id si no viene
        resolved_payment_id = payment_id
        if resolved_payment_id is None:
            # Intentar resolver por idempotency_key canónico
            canonical_idem_key = f"checkout_intent_{intent_id}"
            payment_result = await session.execute(
                select(Payment).where(
                    Payment.auth_user_id == auth_user_id,
                    Payment.idempotency_key == canonical_idem_key,
                )
            )
            payment = payment_result.scalar_one_or_none()
            resolved_payment_id = payment.id if payment else None
        
        # Enviar notificación al admin (idempotente, best-effort)
        # Siempre intentar enviar, con payment_id o "N/A"
        result["admin_notify_sent"] = await send_admin_purchase_notification(
            session=session,
            invoice=invoice,
            intent=intent,
            payment_id=resolved_payment_id,  # Puede ser None, service maneja con "N/A"
            customer_email=user.user_email,
        )
        
        return result
        
    except Exception as e:
        logger.error(
            "purchase_emails_failed: intent=%s auth_user_id=%s error=%s",
            intent_id, str(auth_user_id)[:8], str(e),
        )
        return result


async def handle_stripe_checkout_completed(
    session: AsyncSession,
    event: StripeEvent,
) -> Dict[str, Any]:
    """
    Procesa evento checkout.session.completed de Stripe.
    
    SSOT: Uses intent.auth_user_id for all operations.
    """
    checkout_session = event.data.object
    
    # Extraer metadata
    metadata = checkout_session.get("metadata", {})
    intent_id_str = metadata.get("checkout_intent_id")
    stripe_session_id = checkout_session.get("id")
    
    logger.info(
        "Processing checkout.session.completed: session=%s intent=%s",
        stripe_session_id, intent_id_str,
    )
    
    if not intent_id_str:
        logger.warning(
            "Webhook missing checkout_intent_id in metadata: session=%s",
            stripe_session_id,
        )
        return {
            "status": "ignored",
            "reason": "missing_checkout_intent_id",
            "stripe_session_id": stripe_session_id,
        }
    
    try:
        intent_id = int(intent_id_str)
    except (TypeError, ValueError):
        logger.error("Invalid checkout_intent_id format: %s", intent_id_str)
        return {
            "status": "error",
            "reason": "invalid_checkout_intent_id",
            "stripe_session_id": stripe_session_id,
        }
    
    # Cargar intent
    repo = CheckoutIntentRepository()
    intent = await repo.get_by_id(session, intent_id)
    
    if not intent:
        logger.error("Checkout intent not found: %s", intent_id)
        return {
            "status": "error",
            "reason": "checkout_intent_not_found",
            "checkout_intent_id": intent_id,
            "stripe_session_id": stripe_session_id,
        }
    
    # Actualizar provider_session_id si está vacío
    if not intent.provider_session_id and stripe_session_id:
        intent.provider_session_id = stripe_session_id
    
    # Detectar si el intent estaba expirado (revive)
    was_expired = intent.status == CheckoutIntentStatus.EXPIRED.value
    if was_expired:
        logger.info(
            "Reviving expired intent: intent=%s stripe_session=%s",
            intent_id, stripe_session_id,
        )
    
    # Actualizar intent a COMPLETED si no lo está
    original_status = intent.status
    if intent.status != CheckoutIntentStatus.COMPLETED.value:
        intent.status = CheckoutIntentStatus.COMPLETED.value
        from datetime import datetime, timezone
        if intent.completed_at is None:
            intent.completed_at = datetime.now(timezone.utc)
        await session.flush()
        logger.info(
            "BILLING_INTENT_STATUS_UPDATED intent_id=%d from=%s to=completed",
            intent_id, original_status,
        )
    else:
        logger.info(
            "BILLING_INTENT_ALREADY_COMPLETED intent_id=%d completed_at=%s",
            intent_id, intent.completed_at,
        )
    
    # Finalizar checkout: crear Payment + CreditTransaction (idempotente)
    try:
        finalize_service = BillingFinalizeService()
        result: FinalizeResult = await finalize_service.finalize_checkout_intent(
            session,
            intent_id=intent_id,
        )
        await session.commit()
        
        is_new = result.result == "created"
        
        # =====================================================================
        # LOGGING EXPLÍCITO PARA DIAGNÓSTICO EN RAILWAY (P0)
        # Cada campo debe aparecer en logs para validar flujo SSOT
        # =====================================================================
        logger.info(
            "BILLING_WEBHOOK_FINALIZED "
            "intent_id=%d "
            "finalize_result=%s "
            "payment_id=%d "
            "payment_status=succeeded "
            "paid_at=set "
            "idempotency_key=%s "
            "amount_cents=%d "
            "currency=%s "
            "credits_granted=%d "
            "was_expired=%s "
            "stripe_session=%s",
            intent_id,
            result.result,  # "created" or "already_finalized"
            result.payment_id,
            result.idempotency_key,
            result.amount_cents,
            result.currency,
            result.credits_granted,
            was_expired,
            stripe_session_id,
        )
        
        # SSOT: Use auth_user_id from result
        email_result = await _send_purchase_email_best_effort(
            session, intent_id, result.auth_user_id, result.payment_id
        )
        
        return {
            "status": "success",
            "credits_applied": is_new,
            "credits_amount": result.credits_granted,
            "checkout_intent_id": intent_id,
            "payment_id": result.payment_id,
            "stripe_session_id": stripe_session_id,
            "was_expired": was_expired,
            "finalize_result": result.result,
            "purchase_email_sent": email_result.get("customer_email_sent", False),
            "admin_notify_sent": email_result.get("admin_notify_sent", False),
        }
            
    except ValueError as e:
        logger.error("Failed to finalize checkout for intent %s: %s", intent_id, e)
        return {
            "status": "error",
            "reason": str(e),
            "checkout_intent_id": intent_id,
            "stripe_session_id": stripe_session_id,
        }


async def handle_stripe_checkout_expired(
    session: AsyncSession,
    event: StripeEvent,
) -> Dict[str, Any]:
    """Procesa evento checkout.session.expired de Stripe."""
    checkout_session = event.data.object
    
    metadata = checkout_session.get("metadata", {})
    intent_id_str = metadata.get("checkout_intent_id")
    stripe_session_id = checkout_session.get("id")
    
    logger.info(
        "Processing checkout.session.expired: session=%s intent=%s",
        stripe_session_id, intent_id_str,
    )
    
    if not intent_id_str:
        return {"status": "ignored", "reason": "missing_checkout_intent_id", "stripe_session_id": stripe_session_id}
    
    try:
        intent_id = int(intent_id_str)
    except (TypeError, ValueError):
        return {"status": "error", "reason": "invalid_checkout_intent_id", "stripe_session_id": stripe_session_id}
    
    repo = CheckoutIntentRepository()
    intent = await repo.get_by_id(session, intent_id)
    
    if not intent:
        return {"status": "error", "reason": "checkout_intent_not_found", "checkout_intent_id": intent_id}
    
    if not intent.provider_session_id and stripe_session_id:
        intent.provider_session_id = stripe_session_id
    
    if intent.status in (CheckoutIntentStatus.CREATED.value, CheckoutIntentStatus.PENDING.value):
        intent.status = CheckoutIntentStatus.EXPIRED.value
        await session.commit()
        logger.info("Marked intent as expired via webhook: intent=%s", intent_id)
        return {"status": "success", "expired": True, "checkout_intent_id": intent_id}
    
    return {"status": "success", "expired": False, "reason": "already_final_state", "current_status": intent.status}


async def handle_stripe_billing_webhook(
    session: AsyncSession,
    event: StripeEvent,
) -> Dict[str, Any]:
    """Router principal para webhooks de billing Stripe."""
    event_type = event.type
    
    if event_type == "checkout.session.completed":
        return await handle_stripe_checkout_completed(session, event)
    
    if event_type == "checkout.session.expired":
        return await handle_stripe_checkout_expired(session, event)
    
    logger.debug("Billing webhook ignoring event type: %s", event_type)
    return {"status": "ignored", "reason": "unhandled_event_type", "event_type": event_type}


__all__ = [
    "verify_stripe_webhook_signature",
    "handle_stripe_checkout_completed",
    "handle_stripe_checkout_expired",
    "handle_stripe_billing_webhook",
]
