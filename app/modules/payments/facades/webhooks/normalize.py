# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/webhooks/normalize.py

Normalización REAL de payloads de webhooks de Stripe y PayPal.

Convierte eventos específicos de cada proveedor a un DTO interno estandarizado
para procesamiento uniforme.

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.payments.enums import PaymentProvider
from .constants import (
    STRIPE_EVENT_SUCCESS,
    STRIPE_EVENT_FAILED,
    STRIPE_EVENT_REFUND,
    PAYPAL_EVENT_SUCCESS,
    PAYPAL_EVENT_FAILED,
    PAYPAL_EVENT_REFUND,
)

logger = logging.getLogger(__name__)


class NormalizedWebhook(BaseModel):
    """
    DTO normalizado para eventos de webhook de cualquier proveedor.
    
    Permite procesar eventos de Stripe y PayPal de forma uniforme.
    """
    
    provider: PaymentProvider = Field(description="Proveedor de pago origen")
    event_type: str = Field(description="Tipo de evento original del proveedor")
    event_id: str = Field(description="ID único del evento en el proveedor")
    
    # Identificadores de pago
    payment_id: Optional[int] = Field(
        default=None,
        description="ID interno del Payment (si está en metadata)"
    )
    provider_payment_id: Optional[str] = Field(
        default=None,
        description="ID del pago en el proveedor (payment_intent, capture_id, etc.)"
    )
    provider_session_id: Optional[str] = Field(
        default=None,
        description="ID de la sesión de checkout en el proveedor"
    )
    
    # Estado
    status: str = Field(
        default="unknown",
        description="Estado normalizado: succeeded, failed, pending, refunded"
    )
    is_success: bool = Field(default=False, description="¿Es un evento de éxito?")
    is_failure: bool = Field(default=False, description="¿Es un evento de fallo?")
    is_refund: bool = Field(default=False, description="¿Es un evento de reembolso?")
    
    # Montos
    amount_cents: Optional[int] = Field(
        default=None,
        description="Monto en centavos"
    )
    currency: Optional[str] = Field(
        default=None,
        description="Código de moneda (USD, MXN, etc.)"
    )
    
    # Información de refund
    refund_amount_cents: Optional[int] = Field(
        default=None,
        description="Monto del reembolso en centavos"
    )
    provider_refund_id: Optional[str] = Field(
        default=None,
        description="ID del refund en el proveedor"
    )
    
    # Metadata y payload original
    failure_reason: Optional[str] = Field(
        default=None,
        description="Razón del fallo si aplica"
    )
    customer_id: Optional[str] = Field(
        default=None,
        description="ID del cliente en el proveedor"
    )
    raw: Dict[str, Any] = Field(
        default_factory=dict,
        description="Payload original completo"
    )


class WebhookNormalizationError(ValueError):
    """Error al normalizar un webhook."""
    pass


def _extract_internal_payment_id(metadata: Dict[str, Any]) -> Optional[int]:
    """
    Extrae el payment_id interno de los metadata del evento.
    
    Busca en múltiples campos posibles donde podría estar el ID.
    """
    # Campos donde podría estar el payment_id
    possible_fields = ["payment_id", "internal_payment_id", "doxai_payment_id"]
    
    for field in possible_fields:
        value = metadata.get(field)
        if value is not None:
            try:
                return int(value)
            except (ValueError, TypeError):
                continue
    
    return None


def _normalize_stripe_event(data: Dict[str, Any]) -> NormalizedWebhook:
    """
    Normaliza un evento de Stripe a NormalizedWebhook.
    
    Eventos soportados:
    - checkout.session.completed
    - payment_intent.succeeded
    - payment_intent.payment_failed
    - charge.succeeded
    - charge.failed
    - charge.refunded
    """
    event_type = data.get("type", "")
    event_id = data.get("id", "")
    event_object = data.get("data", {}).get("object", {})
    
    logger.debug(f"Normalizando evento Stripe: {event_type} (ID: {event_id})")
    
    # Extraer información común
    metadata = event_object.get("metadata", {})
    payment_id = _extract_internal_payment_id(metadata)
    
    # Defaults
    result = NormalizedWebhook(
        provider=PaymentProvider.STRIPE,
        event_type=event_type,
        event_id=event_id,
        payment_id=payment_id,
        raw=data,
    )
    
    # Checkout Session Completed
    if event_type == "checkout.session.completed":
        result.provider_session_id = event_object.get("id")
        result.provider_payment_id = event_object.get("payment_intent")
        result.amount_cents = event_object.get("amount_total")
        result.currency = (event_object.get("currency") or "").upper()
        result.customer_id = event_object.get("customer")
        result.status = "succeeded"
        result.is_success = True
        
        # Intentar extraer payment_id de metadata de la sesión
        if not result.payment_id:
            result.payment_id = _extract_internal_payment_id(
                event_object.get("metadata", {})
            )
    
    # Payment Intent Succeeded
    elif event_type == "payment_intent.succeeded":
        result.provider_payment_id = event_object.get("id")
        result.amount_cents = event_object.get("amount")
        result.currency = (event_object.get("currency") or "").upper()
        result.customer_id = event_object.get("customer")
        result.status = "succeeded"
        result.is_success = True
    
    # Payment Intent Failed
    elif event_type == "payment_intent.payment_failed":
        result.provider_payment_id = event_object.get("id")
        result.amount_cents = event_object.get("amount")
        result.currency = (event_object.get("currency") or "").upper()
        result.status = "failed"
        result.is_failure = True
        
        # Extraer razón del fallo
        last_error = event_object.get("last_payment_error", {})
        result.failure_reason = last_error.get("message") or last_error.get("code")
    
    # Charge Succeeded
    elif event_type == "charge.succeeded":
        result.provider_payment_id = event_object.get("payment_intent")
        result.amount_cents = event_object.get("amount")
        result.currency = (event_object.get("currency") or "").upper()
        result.customer_id = event_object.get("customer")
        result.status = "succeeded"
        result.is_success = True
    
    # Charge Failed
    elif event_type == "charge.failed":
        result.provider_payment_id = event_object.get("payment_intent")
        result.amount_cents = event_object.get("amount")
        result.currency = (event_object.get("currency") or "").upper()
        result.status = "failed"
        result.is_failure = True
        result.failure_reason = event_object.get("failure_message")
    
    # Charge Refunded
    elif event_type == "charge.refunded":
        result.provider_payment_id = event_object.get("payment_intent")
        result.amount_cents = event_object.get("amount")
        result.currency = (event_object.get("currency") or "").upper()
        result.status = "refunded"
        result.is_refund = True
        result.refund_amount_cents = event_object.get("amount_refunded")
        
        # Obtener ID del refund más reciente
        refunds = event_object.get("refunds", {}).get("data", [])
        if refunds:
            result.provider_refund_id = refunds[0].get("id")
    
    # Refund Created/Updated
    elif event_type.startswith("refund."):
        result.provider_refund_id = event_object.get("id")
        result.provider_payment_id = event_object.get("payment_intent")
        result.refund_amount_cents = event_object.get("amount")
        result.currency = (event_object.get("currency") or "").upper()
        result.status = "refunded"
        result.is_refund = True
    
    else:
        logger.info(f"Evento Stripe no reconocido, procesando como genérico: {event_type}")
    
    return result


def _normalize_paypal_event(data: Dict[str, Any]) -> NormalizedWebhook:
    """
    Normaliza un evento de PayPal a NormalizedWebhook.
    
    Eventos soportados:
    - PAYMENT.CAPTURE.COMPLETED
    - PAYMENT.CAPTURE.DENIED
    - PAYMENT.CAPTURE.REFUNDED
    - CHECKOUT.ORDER.APPROVED
    - CHECKOUT.ORDER.COMPLETED
    """
    event_type = data.get("event_type", "")
    event_id = data.get("id", "")
    resource = data.get("resource", {})
    
    logger.debug(f"Normalizando evento PayPal: {event_type} (ID: {event_id})")
    
    # Extraer metadata de custom_id o reference_id
    custom_id = resource.get("custom_id") or resource.get("invoice_id") or ""
    metadata = {}
    if custom_id:
        try:
            # Intentar parsear como JSON si es un objeto
            metadata = json.loads(custom_id) if custom_id.startswith("{") else {"payment_id": custom_id}
        except json.JSONDecodeError:
            # Asumir que es el payment_id directamente
            try:
                metadata = {"payment_id": int(custom_id)}
            except ValueError:
                pass
    
    payment_id = _extract_internal_payment_id(metadata)
    
    # Defaults
    result = NormalizedWebhook(
        provider=PaymentProvider.PAYPAL,
        event_type=event_type,
        event_id=event_id,
        payment_id=payment_id,
        raw=data,
    )
    
    # Extraer monto (PayPal usa estructura amount.value en USD/cents)
    amount_obj = resource.get("amount") or resource.get("seller_receivable_breakdown", {}).get("gross_amount", {})
    if amount_obj:
        try:
            value = Decimal(amount_obj.get("value", "0"))
            # PayPal envía el monto en la unidad de la moneda (no centavos)
            result.amount_cents = int(value * 100)
            result.currency = (amount_obj.get("currency_code") or "").upper()
        except (ValueError, TypeError, InvalidOperation):
            pass
    
    # PAYMENT.CAPTURE.COMPLETED
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        result.provider_payment_id = resource.get("id")
        result.status = "succeeded"
        result.is_success = True
    
    # PAYMENT.CAPTURE.DENIED
    elif event_type == "PAYMENT.CAPTURE.DENIED":
        result.provider_payment_id = resource.get("id")
        result.status = "failed"
        result.is_failure = True
        result.failure_reason = resource.get("status_details", {}).get("reason")
    
    # PAYMENT.CAPTURE.REFUNDED
    elif event_type == "PAYMENT.CAPTURE.REFUNDED":
        result.provider_payment_id = resource.get("id")
        result.status = "refunded"
        result.is_refund = True
        
        # El refund amount podría estar en un campo diferente
        refund_breakdown = resource.get("seller_payable_breakdown", {})
        if refund_breakdown:
            try:
                refund_value = Decimal(refund_breakdown.get("gross_amount", {}).get("value", "0"))
                result.refund_amount_cents = int(refund_value * 100)
            except (ValueError, TypeError):
                pass
    
    # CHECKOUT.ORDER.APPROVED
    elif event_type == "CHECKOUT.ORDER.APPROVED":
        result.provider_session_id = resource.get("id")
        result.status = "pending"
        # No marcamos como success hasta que el capture esté completo
    
    # CHECKOUT.ORDER.COMPLETED
    elif event_type == "CHECKOUT.ORDER.COMPLETED":
        result.provider_session_id = resource.get("id")
        result.status = "succeeded"
        result.is_success = True
        
        # Intentar obtener el capture_id de las purchase_units
        purchase_units = resource.get("purchase_units", [])
        if purchase_units:
            captures = purchase_units[0].get("payments", {}).get("captures", [])
            if captures:
                result.provider_payment_id = captures[0].get("id")
    
    # Refund events
    elif "REFUND" in event_type:
        result.provider_refund_id = resource.get("id")
        result.status = "refunded"
        result.is_refund = True
    
    else:
        logger.info(f"Evento PayPal no reconocido, procesando como genérico: {event_type}")
    
    return result


def normalize_webhook_payload(
    provider: PaymentProvider,
    raw_body: bytes,
    headers: Dict[str, str],
) -> NormalizedWebhook:
    """
    Normaliza un payload de webhook al DTO interno.
    
    Args:
        provider: Proveedor de pago (STRIPE o PAYPAL)
        raw_body: Body crudo del request
        headers: Headers del request
    
    Returns:
        NormalizedWebhook con datos extraídos
    
    Raises:
        WebhookNormalizationError: Si el payload no es válido
    """
    # Parsear JSON
    try:
        data = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Error parseando webhook payload: {e}")
        raise WebhookNormalizationError(f"Invalid JSON payload: {e}")
    
    if not isinstance(data, dict):
        raise WebhookNormalizationError("Payload must be a JSON object")
    
    # Normalizar según proveedor
    if provider == PaymentProvider.STRIPE:
        # Validar estructura mínima de Stripe
        if "type" not in data or "id" not in data:
            raise WebhookNormalizationError(
                "Invalid Stripe webhook: missing 'type' or 'id'"
            )
        return _normalize_stripe_event(data)
    
    elif provider == PaymentProvider.PAYPAL:
        # Validar estructura mínima de PayPal
        if "event_type" not in data or "id" not in data:
            raise WebhookNormalizationError(
                "Invalid PayPal webhook: missing 'event_type' or 'id'"
            )
        return _normalize_paypal_event(data)
    
    else:
        raise WebhookNormalizationError(f"Unsupported provider: {provider}")


# Import para compatibilidad (Decimal error handling)
try:
    from decimal import InvalidOperation
except ImportError:
    InvalidOperation = ValueError


__all__ = [
    "normalize_webhook_payload",
    "NormalizedWebhook",
    "WebhookNormalizationError",
]

# Fin del archivo
