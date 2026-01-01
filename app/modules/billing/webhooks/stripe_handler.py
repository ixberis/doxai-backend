# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/webhooks/stripe_handler.py

Handler de webhooks Stripe para billing (checkout de créditos).

Procesa eventos:
- checkout.session.completed: Aplica créditos al usuario + envía email
- checkout.session.expired: Marca intent como expirado

Autor: DoxAI
Fecha: 2025-12-29
Actualizado: 2026-01-01 (email de confirmación de compra)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.config.settings_payments import get_payments_settings
from app.modules.billing.services.checkout_service import apply_checkout_credits
from app.modules.billing.repository import CheckoutIntentRepository
from app.modules.billing.models import CheckoutIntentStatus

# Import condicional de stripe para permitir tests sin el módulo
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    stripe = None  # type: ignore
    STRIPE_AVAILABLE = False

logger = logging.getLogger(__name__)


def verify_stripe_webhook_signature(
    payload: bytes,
    sig_header: str,
    webhook_secret: Optional[str] = None,
) -> stripe.Event:
    """
    Verifica la firma de un webhook de Stripe.
    
    Args:
        payload: Body raw del request
        sig_header: Header Stripe-Signature
        webhook_secret: Secret del webhook (si no se provee, usa env/settings)
        
    Returns:
        stripe.Event verificado
        
    Raises:
        stripe.error.SignatureVerificationError: Si la firma es inválida
        ValueError: Si no hay webhook secret configurado
    """
    settings = get_payments_settings()
    secret = webhook_secret or settings.stripe_webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET")
    
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
    
    event = stripe.Webhook.construct_event(payload, sig_header, secret)
    return event


async def _send_purchase_email_best_effort(
    session: AsyncSession,
    intent_id: int,
    user_id: int,
) -> bool:
    """
    Envía email de confirmación de compra (best-effort).
    
    No propaga excepciones - solo loguea errores.
    
    Args:
        session: Sesión de base de datos
        intent_id: ID del checkout intent
        user_id: ID del usuario
        
    Returns:
        True si se envió, False si falló o ya estaba enviado
    """
    try:
        from app.modules.billing.services.invoice_service import get_invoice_by_intent_id
        from app.modules.billing.services.purchase_email_service import send_purchase_confirmation_email
        from app.modules.billing.repository import CheckoutIntentRepository
        from app.modules.auth.models import AppUser
        
        # Obtener invoice
        invoice = await get_invoice_by_intent_id(session, intent_id)
        if not invoice:
            logger.warning("No invoice found for email: intent=%s", intent_id)
            return False
        
        # Obtener intent
        repo = CheckoutIntentRepository()
        intent = await repo.get_by_id(session, intent_id)
        if not intent:
            logger.warning("Intent not found for email: intent=%s", intent_id)
            return False
        
        # Obtener datos del usuario
        user_result = await session.execute(
            select(AppUser).where(AppUser.user_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user or not user.user_email:
            logger.warning("User or email not found for purchase email: user=%s", user_id)
            return False
        
        # Enviar email (idempotente)
        return await send_purchase_confirmation_email(
            session=session,
            invoice=invoice,
            intent=intent,
            user_email=user.user_email,
            user_name=user.user_full_name,
        )
        
    except Exception as e:
        logger.error(
            "purchase_confirmation_email_failed: intent=%s user=%s error=%s",
            intent_id, user_id, str(e),
        )
        return False


async def handle_stripe_checkout_completed(
    session: AsyncSession,
    event: stripe.Event,
) -> Dict[str, Any]:
    """
    Procesa evento checkout.session.completed de Stripe.
    
    Extrae el checkout_intent_id de metadata y aplica los créditos
    al ledger de forma idempotente. Luego envía email de confirmación.
    
    Args:
        session: Sesión de base de datos
        event: Evento de Stripe verificado
        
    Returns:
        Dict con resultado del procesamiento
    """
    checkout_session = event.data.object
    
    # Extraer metadata
    metadata = checkout_session.get("metadata", {})
    intent_id_str = metadata.get("checkout_intent_id")
    user_id_str = metadata.get("user_id")
    stripe_session_id = checkout_session.get("id")
    
    logger.info(
        "Processing checkout.session.completed: session=%s intent=%s user=%s",
        stripe_session_id, intent_id_str, user_id_str,
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
        logger.error(
            "Invalid checkout_intent_id format: %s",
            intent_id_str,
        )
        return {
            "status": "error",
            "reason": "invalid_checkout_intent_id",
            "stripe_session_id": stripe_session_id,
        }
    
    # Cargar intent para validaciones de seguridad
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
    
    # Validación de seguridad: user_id debe coincidir si viene en metadata
    if user_id_str:
        try:
            metadata_user_id = int(user_id_str)
            if intent.user_id != metadata_user_id:
                logger.error(
                    "User ID mismatch: intent.user_id=%s metadata.user_id=%s",
                    intent.user_id, metadata_user_id,
                )
                return {
                    "status": "error",
                    "reason": "user_id_mismatch",
                    "checkout_intent_id": intent_id,
                    "stripe_session_id": stripe_session_id,
                }
        except (TypeError, ValueError):
            pass  # Ignorar si user_id en metadata no es válido
    
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
    
    # Aplicar créditos (idempotente) - permite transición expired→completed
    try:
        intent, credits_applied = await apply_checkout_credits(
            session,
            intent_id=intent_id,
            stripe_session_id=stripe_session_id,
        )
        await session.commit()
        
        if credits_applied:
            log_msg = "Credits applied for intent %s: %d credits"
            if was_expired:
                log_msg = "[completed_after_expired] " + log_msg
            logger.info(log_msg, intent_id, intent.credits_amount)
            
            # ─────────────────────────────────────────────────────────────
            # ENVIAR EMAIL DE CONFIRMACIÓN (best-effort, no bloquea webhook)
            # ─────────────────────────────────────────────────────────────
            email_sent = await _send_purchase_email_best_effort(
                session, intent_id, intent.user_id
            )
            
            return {
                "status": "success",
                "credits_applied": True,
                "credits_amount": intent.credits_amount,
                "checkout_intent_id": intent_id,
                "stripe_session_id": stripe_session_id,
                "was_expired": was_expired,
                "purchase_email_sent": email_sent,
            }
        else:
            logger.info(
                "Credits already applied for intent %s (idempotent)",
                intent_id,
            )
            
            # ─────────────────────────────────────────────────────────────
            # REINTENTAR EMAIL SI NO SE ENVIÓ (webhook reintentado)
            # ─────────────────────────────────────────────────────────────
            email_sent = False
            try:
                from app.modules.billing.services.invoice_service import get_invoice_by_intent_id
                invoice = await get_invoice_by_intent_id(session, intent_id)
                if invoice and not invoice.purchase_email_sent_at:
                    logger.info(
                        "Retrying purchase email on idempotent webhook: intent=%s",
                        intent_id,
                    )
                    email_sent = await _send_purchase_email_best_effort(
                        session, intent_id, intent.user_id
                    )
            except Exception as e:
                logger.warning(
                    "Failed to retry email on idempotent webhook: intent=%s error=%s",
                    intent_id, str(e),
                )
            
            return {
                "status": "success",
                "credits_applied": False,
                "reason": "already_processed",
                "checkout_intent_id": intent_id,
                "stripe_session_id": stripe_session_id,
                "purchase_email_sent": email_sent,
            }
            
    except ValueError as e:
        logger.error(
            "Failed to apply credits for intent %s: %s",
            intent_id, e,
        )
        return {
            "status": "error",
            "reason": str(e),
            "checkout_intent_id": intent_id,
            "stripe_session_id": stripe_session_id,
        }


async def handle_stripe_checkout_expired(
    session: AsyncSession,
    event: stripe.Event,
) -> Dict[str, Any]:
    """
    Procesa evento checkout.session.expired de Stripe.
    
    Marca el intent como expirado si aún está en created/pending.
    
    Args:
        session: Sesión de base de datos
        event: Evento de Stripe verificado
        
    Returns:
        Dict con resultado del procesamiento
    """
    checkout_session = event.data.object
    
    # Extraer metadata
    metadata = checkout_session.get("metadata", {})
    intent_id_str = metadata.get("checkout_intent_id")
    stripe_session_id = checkout_session.get("id")
    
    logger.info(
        "Processing checkout.session.expired: session=%s intent=%s",
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
    
    # Solo expirar si está en created/pending (idempotencia)
    if intent.status in (
        CheckoutIntentStatus.CREATED.value,
        CheckoutIntentStatus.PENDING.value,
    ):
        intent.status = CheckoutIntentStatus.EXPIRED.value
        await session.commit()
        
        logger.info(
            "Marked intent as expired via webhook: intent=%s session=%s",
            intent_id, stripe_session_id,
        )
        
        return {
            "status": "success",
            "expired": True,
            "checkout_intent_id": intent_id,
            "stripe_session_id": stripe_session_id,
        }
    
    # Ya estaba en otro estado (completed, expired, cancelled) - idempotente
    logger.info(
        "Intent already in final state: intent=%s status=%s",
        intent_id, intent.status,
    )
    return {
        "status": "success",
        "expired": False,
        "reason": "already_final_state",
        "checkout_intent_id": intent_id,
        "stripe_session_id": stripe_session_id,
        "current_status": intent.status,
    }


async def handle_stripe_billing_webhook(
    session: AsyncSession,
    event: stripe.Event,
) -> Dict[str, Any]:
    """
    Router principal para webhooks de billing Stripe.
    
    Despacha al handler apropiado según el tipo de evento.
    
    Args:
        session: Sesión de base de datos
        event: Evento de Stripe verificado
        
    Returns:
        Dict con resultado del procesamiento
    """
    event_type = event.type
    
    if event_type == "checkout.session.completed":
        return await handle_stripe_checkout_completed(session, event)
    
    if event_type == "checkout.session.expired":
        return await handle_stripe_checkout_expired(session, event)
    
    # Eventos no manejados por billing
    logger.debug("Billing webhook ignoring event type: %s", event_type)
    return {
        "status": "ignored",
        "reason": "unhandled_event_type",
        "event_type": event_type,
    }


__all__ = [
    "verify_stripe_webhook_signature",
    "handle_stripe_checkout_completed",
    "handle_stripe_checkout_expired",
    "handle_stripe_billing_webhook",
]
