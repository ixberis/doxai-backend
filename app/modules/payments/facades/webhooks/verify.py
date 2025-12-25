# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/webhooks/verify.py

Fachada de verificación de firmas para webhooks de Stripe y PayPal.

IMPORTANTE:
- En producción, se requiere verificación REAL de firmas.
- El bypass inseguro SOLO funciona si ENVIRONMENT=development.
- PayPal usa verificación async vía API oficial.

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import logging
from typing import Dict

from app.modules.payments.enums import PaymentProvider
from app.modules.payments.services.webhooks.signature_verification import (
    verify_stripe_signature as _verify_stripe,
    verify_paypal_signature as _verify_paypal,
    _is_development_environment,
)
from app.shared.config.settings_payments import get_payments_settings

logger = logging.getLogger(__name__)


def verify_stripe_signature(
    raw_body: bytes,
    headers: Dict[str, str],
    # Inyección de dependencias para testing
    settings=None,
) -> bool:
    """
    Verifica la firma de un webhook de Stripe.
    
    Args:
        raw_body: Body crudo del request
        headers: Headers del request (debe incluir Stripe-Signature)
        settings: Configuración de pagos (opcional, para testing)
    
    Returns:
        True si la firma es válida
    """
    if settings is None:
        settings = get_payments_settings()
    
    # Extraer header de firma (case-insensitive)
    signature_header = None
    for key, value in headers.items():
        if key.lower() == "stripe-signature":
            signature_header = value
            break
    
    return _verify_stripe(
        payload=raw_body,
        signature_header=signature_header,
        webhook_secret=settings.stripe_webhook_secret,
        tolerance_seconds=settings.stripe_webhook_tolerance_seconds,
    )


async def verify_paypal_signature(raw_body: bytes, headers: Dict[str, str]) -> bool:
    """
    Verifica la firma de un webhook de PayPal (async).
    
    Args:
        raw_body: Body crudo del request
        headers: Headers del request (debe incluir headers PayPal-*)
    
    Returns:
        True si la firma es válida
    """
    settings = get_payments_settings()
    
    # Extraer headers de PayPal (case-insensitive)
    def get_header(name: str) -> str | None:
        name_lower = name.lower()
        for key, value in headers.items():
            if key.lower() == name_lower:
                return value
        return None
    
    return await _verify_paypal(
        payload=raw_body,
        transmission_id=get_header("paypal-transmission-id"),
        transmission_sig=get_header("paypal-transmission-sig"),
        cert_url=get_header("paypal-cert-url"),
        transmission_time=get_header("paypal-transmission-time"),
        webhook_id=settings.paypal_webhook_id,
        auth_algo=get_header("paypal-auth-algo"),
    )


async def verify_webhook_signature(
    provider: PaymentProvider,
    raw_body: bytes,
    headers: Dict[str, str],
) -> bool:
    """
    Verifica la firma de un webhook según el proveedor.
    
    Args:
        provider: Proveedor de pago (STRIPE o PAYPAL)
        raw_body: Body crudo del request
        headers: Headers del request
    
    Returns:
        True si la firma es válida
    
    Raises:
        ValueError: Si el proveedor no es soportado
    """
    if provider == PaymentProvider.STRIPE:
        return verify_stripe_signature(raw_body, headers)
    elif provider == PaymentProvider.PAYPAL:
        return await verify_paypal_signature(raw_body, headers)
    else:
        logger.error(f"Proveedor de pago no soportado: {provider}")
        raise ValueError(f"Unsupported payment provider: {provider}")


__all__ = [
    "verify_stripe_signature",
    "verify_paypal_signature",
    "verify_webhook_signature",
]

# Fin del archivo
