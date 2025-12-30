# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/webhook_routes.py

Rutas de webhooks para billing (checkout de créditos).

Endpoint:
- POST /api/billing/webhooks/stripe

Autor: DoxAI
Fecha: 2025-12-29
"""

from __future__ import annotations

import logging
from typing import Any, Dict, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.shared.config.settings_payments import get_payments_settings
from .webhooks.stripe_handler import (
    verify_stripe_webhook_signature,
    handle_stripe_billing_webhook,
)

# Import condicional de stripe para permitir tests sin el módulo
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    stripe = None  # type: ignore
    STRIPE_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/billing/webhooks",
    tags=["billing:webhooks"],
)


@router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
)
async def stripe_billing_webhook(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """
    Webhook de Stripe para billing (checkout de créditos).
    
    Procesa eventos:
    - checkout.session.completed: Aplica créditos al usuario
    
    Requiere header Stripe-Signature para validación.
    """
    settings = get_payments_settings()
    
    # Obtener body raw y signature header
    raw_body = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    
    if not sig_header:
        logger.warning("Webhook received without Stripe-Signature header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header",
        )
    
    # Verificar firma (a menos que estemos en modo inseguro para dev)
    try:
        if not STRIPE_AVAILABLE:
            raise ValueError("Stripe SDK not available")
        
        if settings.allow_insecure_webhooks:
            logger.warning("INSECURE: Skipping webhook signature verification")
            import json
            event_data = json.loads(raw_body)
            event = stripe.Event.construct_from(event_data, stripe.api_key)
        else:
            event = verify_stripe_webhook_signature(raw_body, sig_header)
    except ValueError as e:
        logger.error("Webhook configuration error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook not configured",
        )
    except Exception as e:
        # Handle SignatureVerificationError when stripe is available
        if STRIPE_AVAILABLE and isinstance(e, stripe.error.SignatureVerificationError):
            logger.warning("Invalid webhook signature: %s", e)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )
        raise
    
    logger.info(
        "Billing webhook received: type=%s id=%s",
        event.type, event.id,
    )
    
    # Procesar evento
    try:
        result = await handle_stripe_billing_webhook(session, event)
        return result
    except Exception as e:
        logger.exception("Error processing billing webhook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing error: {str(e)}",
        )


__all__ = ["router"]
