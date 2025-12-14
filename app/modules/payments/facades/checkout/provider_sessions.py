
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/checkout/provider_sessions.py

Abstracción de creación de sesiones de checkout por proveedor.
Aquí se encapsula la integración específica con Stripe y PayPal.

IMPORTANTE:
- En esta Fase 3 definimos la interfaz y un stub seguro.
- La lógica real de integración con las APIs de Stripe/PayPal
  se puede implementar en una fase posterior sin romper la API.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any

from app.modules.payments.enums import Currency, PaymentProvider
from .dto import ProviderCheckoutInfo


def generate_idempotency_key(
    *,
    user_id: str,
    provider: PaymentProvider,
    amount_cents: int,
    credits_purchased: int,
    success_url: str,
    cancel_url: str,
    client_nonce: str,
) -> str:
    """
    Genera una clave idempotente estable basada en los parámetros del checkout.
    
    Mismos parámetros → misma clave (útil para evitar doble cobro).
    """
    parts = [
        str(user_id),
        str(provider.value if hasattr(provider, "value") else provider),
        str(amount_cents),
        str(credits_purchased),
        success_url,
        cancel_url,
        client_nonce,
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def create_stripe_checkout_session(
    *,
    amount: Decimal,
    currency: Currency,
    payment_id: int,
    user_id: str,
    idempotency_key: str,
    success_url: Optional[str],
    cancel_url: Optional[str],
) -> ProviderCheckoutInfo:
    """
    Crea una sesión de pago en Stripe.

    Stub actual:
    - No realiza llamada real a Stripe.
    - Devuelve un objeto ProviderCheckoutInfo con datos simulados.

    En una fase posterior se puede integrar stripe-python o llamadas HTTP
    reales utilizando las claves configuradas en settings.
    """

    # NOTA: Este stub permite que las pruebas funcionen sin dependencia externa.
    fake_client_secret = f"pi_{payment_id}_secret_fake"
    return ProviderCheckoutInfo(
        provider_session_id=f"stripe_pi_{payment_id}",
        redirect_url=None,
        client_secret=fake_client_secret,
    )


async def create_paypal_checkout_session(
    *,
    amount: Decimal,
    currency: Currency,
    payment_id: int,
    user_id: str,
    idempotency_key: str,
    success_url: Optional[str],
    cancel_url: Optional[str],
) -> ProviderCheckoutInfo:
    """
    Crea una orden de pago en PayPal.

    Stub actual:
    - No realiza llamada real a PayPal.
    - Devuelve un objeto ProviderCheckoutInfo con una URL simulada.

    La integración real puede implementarse más adelante usando la
    REST API de PayPal.
    """

    fake_approval_url = f"https://paypal.example/checkout?payment_id={payment_id}"
    return ProviderCheckoutInfo(
        provider_session_id=f"paypal_order_{payment_id}",
        redirect_url=fake_approval_url,
        client_secret=None,
    )


async def create_provider_checkout_session(
    *,
    provider: PaymentProvider,
    amount: Decimal,
    currency: Currency,
    payment_id: int,
    user_id: str,
    idempotency_key: str,
    success_url: Optional[str],
    cancel_url: Optional[str],
) -> ProviderCheckoutInfo:
    """
    Punto de entrada unificado para crear sesiones de checkout
    según el proveedor.
    """

    if provider == PaymentProvider.STRIPE:
        return await create_stripe_checkout_session(
            amount=amount,
            currency=currency,
            payment_id=payment_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            success_url=success_url,
            cancel_url=cancel_url,
        )

    if provider == PaymentProvider.PAYPAL:
        return await create_paypal_checkout_session(
            amount=amount,
            currency=currency,
            payment_id=payment_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
            success_url=success_url,
            cancel_url=cancel_url,
        )

    # Esto no debería ocurrir gracias a los validadores previos
    raise ValueError(f"Unsupported provider: {provider}")


async def create_provider_session(
    *,
    provider: PaymentProvider,
    user_id: str,
    currency: Currency,
    credits_purchased: int,
    amount_cents: int,
    idempotency_key: str,
    success_url: str,
    cancel_url: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, datetime]:
    """
    Función legacy que retorna tupla (provider_payment_id, url, expires_at).
    
    Wrapper sobre create_provider_checkout_session para compatibilidad con tests.
    """
    amount = Decimal(amount_cents) / Decimal(100)
    
    # Usamos payment_id ficticio para el stub
    fake_payment_id = abs(hash(idempotency_key)) % 1000000
    
    info = await create_provider_checkout_session(
        provider=provider,
        amount=amount,
        currency=currency,
        payment_id=fake_payment_id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    
    # Construir URL de redirección
    if info.redirect_url:
        url = info.redirect_url
    else:
        # Para Stripe, construimos URL ficticia
        url = f"https://checkout.stripe.com/pay/{info.provider_session_id}"
    
    # Tiempo de expiración (24 horas)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    
    return (info.provider_session_id, url, expires_at)


__all__ = [
    "generate_idempotency_key",
    "create_stripe_checkout_session",
    "create_paypal_checkout_session",
    "create_provider_checkout_session",
    "create_provider_session",
]

# Fin del archivo backend/app/modules/payments/facades/checkout/provider_sessions.py