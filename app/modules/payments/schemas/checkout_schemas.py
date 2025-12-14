
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/schemas/checkout_schemas.py

Esquemas Pydantic para el flujo de inicio de checkout
de créditos prepagados (API v3).

Autor: Ixchel Beristain
Fecha: 2025-11-21 (v3)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.modules.payments.enums import PaymentProvider, Currency


class CheckoutRequest(BaseModel):
    """
    Request para iniciar un checkout de créditos prepagados.
    
    MODO RECOMENDADO (anti-fraude):
    - Enviar solo `package_id` + `provider` + URLs
    - Backend resuelve amount/credits desde billing.get_package_by_id()
    
    MODO LEGACY (deprecated):
    - Enviar `credits` + `amount` directamente
    - Solo funciona si NO se envía package_id
    """

    provider: PaymentProvider = Field(
        description="Proveedor de pago a utilizar (stripe | paypal)."
    )
    
    # --- MODO ANTI-FRAUDE: package_id como fuente de verdad ---
    package_id: Optional[str] = Field(
        default=None,
        description=(
            "ID del paquete de créditos (e.g., 'pkg_pro'). "
            "Si se proporciona, amount y credits se ignoran y se resuelven desde backend."
        ),
    )
    
    # --- MODO LEGACY (deprecated) ---
    currency: Currency = Field(
        default=Currency.MXN,
        description="Moneda en la que se cobrará el pago (ignorado si package_id presente).",
    )
    credits: Optional[int] = Field(
        default=None,
        gt=0,
        description="[DEPRECATED] Cantidad de créditos a adquirir. Ignorado si package_id presente.",
    )
    amount: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="[DEPRECATED] Monto total del pago. Ignorado si package_id presente.",
    )
    
    # --- Campos comunes ---
    idempotency_key: Optional[str] = Field(
        default=None,
        description=(
            "Clave idempotente opcional para identificar el intento de checkout. "
            "Si no se proporciona, el backend generará una."
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

    @model_validator(mode="after")
    def validate_package_or_legacy(self) -> "CheckoutRequest":
        """
        Valida que se proporcione package_id O (credits + amount), nunca ambos.
        
        - Si viene package_id: credits y amount deben ser None
        - Si no viene package_id: credits y amount son requeridos
        """
        has_package = self.package_id is not None
        has_legacy = self.credits is not None or self.amount is not None
        
        if has_package and has_legacy:
            raise ValueError(
                "No se puede enviar 'package_id' junto con 'credits' o 'amount'. "
                "Use solo 'package_id' (recomendado) o solo 'credits' + 'amount' (legacy)."
            )
        
        if not has_package:
            # Modo legacy: requiere ambos credits y amount
            if self.credits is None or self.amount is None:
                raise ValueError(
                    "Debe proporcionar 'package_id' o ambos 'credits' y 'amount'"
                )
        
        return self


class ProviderCheckoutInfo(BaseModel):
    """
    Información específica del proveedor para completar el checkout en frontend.
    """

    provider_session_id: Optional[str] = Field(
        default=None,
        description="Identificador de sesión u orden en el proveedor.",
    )
    redirect_url: Optional[str] = Field(
        default=None,
        description="URL a la que debe redirigirse el usuario (si aplica).",
    )
    client_secret: Optional[str] = Field(
        default=None,
        description="Client secret de Stripe (si aplica).",
    )


class CheckoutResponse(BaseModel):
    """
    Respuesta estándar al iniciar un checkout.

    El frontend utilizará esta información para completar
    la redirección o el flujo de pago embebido.
    """

    payment_id: int = Field(description="ID interno del pago en DoxAI.")
    provider: PaymentProvider = Field(
        description="Proveedor de pago utilizado para este checkout."
    )
    provider_info: ProviderCheckoutInfo = Field(
        description="Información específica del proveedor para la UI."
    )


__all__ = [
    "CheckoutRequest",
    "CheckoutResponse",
    "ProviderCheckoutInfo",
]

# Fin del archivo backend/app/modules/payments/schemas/checkout_schemas.py
