
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/checkout/dto.py

DTOs para el flujo de inicio de checkout de créditos prepagados.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.modules.payments.enums import PaymentProvider, Currency


class CheckoutRequest(BaseModel):
    """
    Payload de entrada para iniciar un checkout.

    En este modelo simplificado:
    - credits: número de créditos a comprar
    - amount: monto total a cobrar (en la moneda indicada)
    """

    provider: PaymentProvider = Field(
        description="Proveedor de pago a utilizar (stripe | paypal)."
    )
    currency: Currency = Field(
        default=Currency.MXN, description="Moneda en la que se cobrará el pago."
    )
    credits: int = Field(gt=0, description="Cantidad de créditos a adquirir.")
    amount: Decimal = Field(gt=0, description="Monto total del pago.")
    idempotency_key: Optional[str] = Field(
        default=None,
        description=(
            "Clave idempotente opcional para identificar el intento de checkout "
            "(si no se proporciona, el backend generará una)."
        ),
    )
    success_url: Optional[HttpUrl] = Field(
        default=None,
        description="URL a la que el proveedor redirigirá en caso de éxito.",
    )
    cancel_url: Optional[HttpUrl] = Field(
        default=None,
        description="URL a la que el proveedor redirigirá en caso de cancelación.",
    )

    @field_validator("credits")
    @classmethod
    def validate_credits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("credits must be > 0")
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be > 0")
        return value


class ProviderCheckoutInfo(BaseModel):
    """
    Información específica del proveedor para completar el checkout en frontend.

    - Stripe: normalmente usaremos client_secret.
    - PayPal: normalmente approval_url / provider_session_id.
    """

    provider_session_id: Optional[str] = None
    redirect_url: Optional[str] = None
    client_secret: Optional[str] = None


class CheckoutResponse(BaseModel):
    """
    Respuesta estándar al iniciar un checkout.

    Siempre se devuelve:
    - payment_id: ID interno del registro Payment.
    - provider: proveedor utilizado.

    Y se añade información específica del proveedor en provider_info.
    """

    payment_id: int
    provider: PaymentProvider
    provider_info: ProviderCheckoutInfo


__all__ = [
    "CheckoutRequest",
    "CheckoutResponse",
    "ProviderCheckoutInfo",
]

# Fin del archivo backend/app/modules/payments/facades/checkout/dto.py