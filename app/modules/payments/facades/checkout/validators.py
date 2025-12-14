
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/checkout/validators.py

Validadores de negocio para el flujo de checkout.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.payments.enums import PaymentProvider, Currency
from .dto import CheckoutRequest


class CheckoutValidationError(ValueError):
    """Error de validación de negocio en el flujo de checkout."""


def validate_checkout_request(data: CheckoutRequest) -> None:
    """
    Validaciones adicionales a las de Pydantic
    (por ahora muy simples, pero escalables).
    """

    if data.credits <= 0:
        raise CheckoutValidationError("credits must be greater than 0")

    if data.amount <= Decimal("0"):
        raise CheckoutValidationError("amount must be greater than 0")

    if data.provider not in (PaymentProvider.STRIPE, PaymentProvider.PAYPAL):
        raise CheckoutValidationError("Unsupported payment provider")

    if data.currency not in (Currency.MXN, Currency.USD):
        raise CheckoutValidationError("Unsupported currency")


def validate_checkout_params(
    *,
    amount_cents: int,
    credits_purchased: int,
    success_url: str,
    cancel_url: str,
) -> None:
    """
    Validación de parámetros de checkout (usado por tests y rutas legacy).
    """
    from fastapi import HTTPException
    import os

    if amount_cents <= 0:
        raise HTTPException(status_code=422, detail="amount must be greater than 0")
    
    if credits_purchased <= 0:
        raise HTTPException(status_code=422, detail="credits must be greater than 0")
    
    allow_http_localhost = os.getenv("ALLOW_HTTP_LOCALHOST") == "1"
    
    for url_name, url in [("success_url", success_url), ("cancel_url", cancel_url)]:
        if not url:
            raise HTTPException(status_code=422, detail=f"{url_name} is required")
        
        if not url.startswith(("https://", "http://")):
            raise HTTPException(status_code=422, detail=f"{url_name} must be a valid URL")
        
        if url.startswith("http://") and not (allow_http_localhost and "localhost" in url):
            raise HTTPException(status_code=422, detail=f"{url_name} must use HTTPS")


__all__ = [
    "CheckoutValidationError",
    "validate_checkout_request",
    "validate_checkout_params",
]

# Fin del archivo backend/app/modules/payments/facades/checkout/validators.py
