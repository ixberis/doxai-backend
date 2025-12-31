# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/schemas.py

Esquemas Pydantic para el módulo de billing (checkout de créditos).

Autor: DoxAI
Fecha: 2025-12-29
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class BillingCheckoutRequest(BaseModel):
    """
    Request para iniciar un checkout de créditos prepagados.
    
    Modo simplificado: solo package_id + idempotency_key.
    El backend resuelve amount/credits desde billing.get_package_by_id().
    """
    
    package_id: str = Field(
        description="ID del paquete de créditos (e.g., 'pkg_starter', 'pkg_pro').",
        min_length=1,
        max_length=50,
    )
    
    idempotency_key: str = Field(
        description="Clave idempotente única para identificar el intento de checkout.",
        min_length=1,
        max_length=100,
    )


class BillingCheckoutResponse(BaseModel):
    """
    Respuesta al iniciar un checkout de créditos.
    
    El frontend utilizará checkout_url para redirigir al usuario
    al flujo de pago (cuando esté implementado).
    """
    
    checkout_url: str = Field(
        description="URL a la que debe redirigirse el usuario para completar el pago."
    )
    
    checkout_intent_id: Optional[int] = Field(
        default=None,
        description="ID interno del intent de checkout (para referencia/polling)."
    )


class CheckoutStatusResponse(BaseModel):
    """
    Respuesta del endpoint de estado de checkout.
    
    Usado para polling: FE consulta hasta que status sea final.
    """
    
    checkout_intent_id: int = Field(
        description="ID del intent de checkout."
    )
    
    status: str = Field(
        description="Estado: created, pending, completed, expired, cancelled."
    )
    
    provider: Optional[str] = Field(
        default=None,
        description="Proveedor de pago (stripe, paypal) o null."
    )
    
    provider_session_id: Optional[str] = Field(
        default=None,
        description="ID de sesión del proveedor o null."
    )
    
    credits_amount: int = Field(
        description="Cantidad de créditos del paquete."
    )
    
    created_at: datetime = Field(
        description="Fecha de creación del intent."
    )
    
    updated_at: datetime = Field(
        description="Última actualización del intent."
    )



# Error codes para checkout - alineados con frontend CHECKOUT_ERRORS
class BillingCheckoutErrorCodes:
    """Códigos de error estandarizados para checkout."""
    INVALID_PACKAGE = "invalid_package"
    PAYMENTS_NOT_READY = "payments_not_ready"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    AUTHENTICATION_REQUIRED = "authentication_required"


class CheckoutHistoryItem(BaseModel):
    """Item individual en la lista de historial de checkouts."""
    
    id: int = Field(description="ID del checkout intent.")
    status: str = Field(description="Estado: created, pending, completed, expired, cancelled.")
    credits_amount: int = Field(description="Cantidad de créditos.")
    price_cents: int = Field(description="Precio en centavos.")
    currency: str = Field(description="Moneda (USD, MXN, etc.).")
    provider: Optional[str] = Field(default=None, description="Proveedor de pago.")
    created_at: datetime = Field(description="Fecha de creación.")
    updated_at: datetime = Field(description="Última actualización.")


class CheckoutHistoryResponse(BaseModel):
    """Respuesta paginada de historial de checkouts."""
    
    items: list[CheckoutHistoryItem] = Field(description="Lista de checkouts.")
    total: int = Field(description="Total de checkouts del usuario.")
    limit: int = Field(description="Límite por página.")
    offset: int = Field(description="Offset actual.")


class ReceiptListItem(BaseModel):
    """Item en la lista de recibos (solo checkouts completados)."""
    
    intent_id: int = Field(description="ID del checkout intent.")
    status: str = Field(description="Estado (siempre 'completed').")
    credits: int = Field(description="Créditos adquiridos.")
    amount: int = Field(description="Monto en centavos.")
    currency: str = Field(description="Moneda (USD, MXN, etc.).")
    purchased_at: datetime = Field(description="Fecha de compra.")


class ReceiptListResponse(BaseModel):
    """Respuesta del listado de recibos."""
    
    items: list[ReceiptListItem] = Field(description="Lista de recibos.")
    next_cursor: Optional[str] = Field(default=None, description="Cursor para siguiente página.")


class CheckoutReceiptResponse(BaseModel):
    """
    Respuesta del endpoint de recibo de checkout.
    
    Solo disponible para checkouts completed.
    """
    
    checkout_intent_id: int = Field(
        description="ID del intent de checkout."
    )
    
    status: str = Field(
        description="Estado del checkout (debe ser 'completed')."
    )
    
    credits_amount: int = Field(
        description="Cantidad de créditos adquiridos."
    )
    
    price_cents: int = Field(
        description="Precio pagado en centavos."
    )
    
    currency: str = Field(
        description="Moneda del pago (USD, MXN, etc.)."
    )
    
    provider: Optional[str] = Field(
        default=None,
        description="Proveedor de pago (stripe, paypal)."
    )
    
    provider_session_id: Optional[str] = Field(
        default=None,
        description="ID de sesión del proveedor."
    )
    
    created_at: datetime = Field(
        description="Fecha de creación del checkout."
    )
    
    completed_at: datetime = Field(
        description="Fecha de completado del checkout."
    )


__all__ = [
    "BillingCheckoutRequest",
    "BillingCheckoutResponse",
    "BillingCheckoutErrorCodes",
    "CheckoutStatusResponse",
    "CheckoutHistoryItem",
    "CheckoutHistoryResponse",
    "CheckoutReceiptResponse",
    "ReceiptListItem",
    "ReceiptListResponse",
]
