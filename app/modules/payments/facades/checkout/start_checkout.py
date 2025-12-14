
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/checkout/start_checkout.py

Fachada de alto nivel para iniciar un checkout de créditos prepagados.

Orquesta:
- Validación de payload (CheckoutRequest)
- Creación de Payment interno (PaymentService)
- Creación de sesión de checkout en el proveedor
- Actualización del payment con payment_intent_id/provider_session_id
- Construcción de CheckoutResponse para el frontend

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import PaymentProvider, Currency
from app.modules.payments.services.payment_service import PaymentService
from .dto import CheckoutRequest, CheckoutResponse, ProviderCheckoutInfo
from .validators import validate_checkout_request
from .provider_sessions import create_provider_checkout_session


async def start_checkout(
    session: AsyncSession,
    *,
    user_id: str,
    payload: CheckoutRequest,
    payment_service: PaymentService,
) -> CheckoutResponse:
    """
    Inicia un checkout de créditos prepagados para el usuario indicado.

    Devuelve un CheckoutResponse que el frontend utilizará para:
    - completar la interfaz de pago (Stripe client_secret / PayPal redirect_url),
    - mostrar información del pago creado.
    """

    # 1) Validaciones de negocio
    validate_checkout_request(payload)

    # 2) Clave idempotente (si el cliente no la envió)
    idempotency_key = payload.idempotency_key or f"checkout:{user_id}:{uuid4().hex}"

    # 3) Crear/obtener Payment interno (idempotente por idempotency_key)
    payment = await payment_service.create_payment(
        session,
        user_id=user_id,
        provider=payload.provider,
        currency=payload.currency,
        amount=payload.amount,
        credits_awarded=payload.credits,
        idempotency_key=idempotency_key,
        payment_intent_id=None,
        metadata={
            "success_url": str(payload.success_url) if payload.success_url else None,
            "cancel_url": str(payload.cancel_url) if payload.cancel_url else None,
        },
    )

    # 4) Crear sesión en el proveedor
    provider_info: ProviderCheckoutInfo = await create_provider_checkout_session(
        provider=payload.provider,
        amount=payload.amount,
        currency=payload.currency,
        payment_id=payment.id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        success_url=str(payload.success_url) if payload.success_url else None,
        cancel_url=str(payload.cancel_url) if payload.cancel_url else None,
    )

    # 5) Actualizar payment_intent_id si aplica (opcional, pero útil)
    if provider_info.provider_session_id and payment.payment_intent_id is None:
        payment.payment_intent_id = provider_info.provider_session_id
        await session.flush()

    # 6) Armar respuesta estándar
    response = CheckoutResponse(
        payment_id=payment.id,
        provider=payload.provider,
        provider_info=provider_info,
    )
    return response


__all__ = ["start_checkout"]

# Fin del archivo backend/app/modules/payments/facades/checkout/start_checkout.py
