# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/payments/webhook_handler.py

Entrada unificada para procesar webhooks de Stripe o PayPal.

Pasos:
1. Verificar firma mediante signature_verification (OBLIGATORIO en producción)
2. Normalizar el payload a un formato común
3. Registrar PaymentEvent (idempotente)
4. Identificar tipo de evento (success / failure / refund)
5. Delegar en success / refund / failure handlers
6. Retornar dict estandarizado para la API

IMPORTANTE:
- La verificación de firma es OBLIGATORIA en producción.
- El bypass solo funciona en ENVIRONMENT=development.

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import PaymentStatus, PaymentProvider
from app.modules.payments.services.payment_service import PaymentService
from app.modules.payments.services.refund_service import RefundService
from app.modules.payments.services.payment_event_service import PaymentEventService
from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.repositories.refund_repository import RefundRepository

from app.modules.payments.facades.webhooks.verify import verify_webhook_signature
from app.modules.payments.facades.webhooks.normalize import (
    normalize_webhook_payload,
    WebhookNormalizationError,
)
from app.modules.payments.facades.webhooks.success import (
    handle_payment_success,
    handle_payment_failure,
    handle_payment_refund,
)

logger = logging.getLogger(__name__)


class WebhookSignatureError(Exception):
    """Error de verificación de firma de webhook."""
    pass


class WebhookProcessingError(Exception):
    """Error durante el procesamiento del webhook."""
    pass


async def handle_webhook(
    session: AsyncSession,
    *,
    provider: PaymentProvider,
    raw_body: bytes,
    headers: Dict[str, str],
    payment_service: PaymentService,
    payment_repo: PaymentRepository,
    refund_service: RefundService,
    refund_repo: RefundRepository,
    event_service: PaymentEventService,
) -> Dict[str, Any]:
    """
    Procesa un webhook del proveedor (Stripe o PayPal).
    
    Este es el punto de entrada principal para webhooks.
    Toda acreditación de créditos pasa por aquí.
    
    Args:
        session: Sesión de base de datos
        provider: Proveedor de pago
        raw_body: Body crudo del request
        headers: Headers del request
        payment_service: Servicio de pagos
        payment_repo: Repositorio de pagos
        refund_service: Servicio de refunds
        refund_repo: Repositorio de refunds
        event_service: Servicio de eventos
    
    Returns:
        Dict con status del procesamiento
    
    Raises:
        WebhookSignatureError: Si la firma es inválida
        WebhookProcessingError: Si hay error en el procesamiento
    """
    provider_name = provider.value.upper()
    
    # 1) VERIFICAR FIRMA (OBLIGATORIO EN PRODUCCIÓN)
    logger.info(f"Procesando webhook de {provider_name}")
    
    signature_valid = await verify_webhook_signature(provider, raw_body, headers)
    
    if not signature_valid:
        logger.error(f"Webhook {provider_name} rechazado: firma inválida")
        raise WebhookSignatureError(
            f"Invalid {provider_name} webhook signature. "
            "Ensure the webhook secret is configured correctly."
        )
    
    logger.debug(f"Webhook {provider_name}: firma verificada")
    
    # 2) NORMALIZAR PAYLOAD
    try:
        normalized = normalize_webhook_payload(provider, raw_body, headers)
    except WebhookNormalizationError as e:
        logger.error(f"Webhook {provider_name} error de normalización: {e}")
        raise WebhookProcessingError(f"Failed to normalize webhook: {e}")
    
    logger.info(
        f"Webhook {provider_name} normalizado: "
        f"event_type={normalized.event_type}, "
        f"event_id={normalized.event_id}, "
        f"payment_id={normalized.payment_id}, "
        f"is_success={normalized.is_success}"
    )
    
    # Validar que tenemos payment_id para eventos que lo requieren
    if normalized.payment_id is None and (normalized.is_success or normalized.is_refund):
        # Intentar buscar por provider_payment_id
        if normalized.provider_payment_id:
            payment = await payment_repo.get_by_provider_payment_id(
                session, 
                provider=provider,
                provider_payment_id=normalized.provider_payment_id
            )
            if payment:
                normalized.payment_id = payment.id
                logger.info(f"Payment encontrado por provider_payment_id: {payment.id}")
    
    # Si aún no tenemos payment_id y el evento requiere correlación → ignorar
    # NUNCA registrar eventos con payment_id=0
    if normalized.payment_id is None and (normalized.is_success or normalized.is_failure or normalized.is_refund):
        logger.warning(
            f"Webhook {provider_name} ignorado: no se pudo determinar payment_id. "
            f"Evento: {normalized.event_type}, ID: {normalized.event_id}"
        )
        return {
            "status": "ignored",
            "reason": "payment_id not found in webhook",
            "event_type": normalized.event_type,
            "event_id": normalized.event_id,
        }
    
    # 3) REGISTRAR EVENTO (idempotente) - Solo si tenemos payment_id válido
    if normalized.payment_id is not None:
        try:
            event = await event_service.register_event(
                session,
                payment_id=normalized.payment_id,
                provider_event_id=normalized.event_id,
                event_type=normalized.event_type,
                payload=normalized.raw,
            )
            
            # Si el evento ya existía, es un duplicado
            if event and hasattr(event, '_was_existing') and event._was_existing:
                logger.info(f"Webhook {provider_name} duplicado, ignorando: {normalized.event_id}")
                return {
                    "status": "duplicate",
                    "event_id": normalized.event_id,
                    "message": "Event already processed",
                }
                
        except Exception as e:
            logger.error(f"Error registrando evento: {e}")
            # Continuamos aunque falle el registro del evento
    
    # 4) DESPACHAR SEGÚN TIPO DE EVENTO
    
    # Éxito de pago
    if normalized.is_success:
        try:
            payment = await handle_payment_success(
                session=session,
                payment_service=payment_service,
                payment_repo=payment_repo,
                payment_id=normalized.payment_id,
            )
            
            logger.info(
                f"Pago {payment.id} acreditado exitosamente via webhook {provider_name}"
            )
            
            return {
                "status": "ok",
                "event": "payment_succeeded",
                "payment_id": payment.id,
                "credits_awarded": getattr(payment, 'credits_awarded', 0),
            }
            
        except Exception as e:
            logger.error(f"Error procesando éxito de pago: {e}")
            raise WebhookProcessingError(f"Failed to process payment success: {e}")
    
    # Fallo de pago
    if normalized.is_failure:
        try:
            payment = await handle_payment_failure(
                session=session,
                payment_service=payment_service,
                payment_repo=payment_repo,
                payment_id=normalized.payment_id,
                reason=normalized.failure_reason,
            )
            
            logger.info(f"Pago {payment.id} marcado como fallido via webhook")
            
            return {
                "status": "ok",
                "event": "payment_failed",
                "payment_id": payment.id,
                "reason": normalized.failure_reason,
            }
            
        except ValueError as e:
            # Payment no encontrado
            logger.warning(f"Payment no encontrado para fallo: {e}")
            return {
                "status": "ignored",
                "event": "payment_failed",
                "reason": str(e),
            }
        except Exception as e:
            logger.error(f"Error procesando fallo de pago: {e}")
            raise WebhookProcessingError(f"Failed to process payment failure: {e}")
    
    # Refund
    if normalized.is_refund:
        try:
            refund = await handle_payment_refund(
                session=session,
                refund_service=refund_service,
                refund_repo=refund_repo,
                payment_repo=payment_repo,
                normalized=normalized,
            )
            
            logger.info(f"Refund {refund.id} procesado via webhook")
            
            return {
                "status": "ok",
                "event": "refund_processed",
                "refund_id": refund.id,
                "payment_id": normalized.payment_id,
            }
            
        except ValueError as e:
            logger.warning(f"Error procesando refund: {e}")
            return {
                "status": "ignored",
                "event": "refund_failed",
                "reason": str(e),
            }
        except Exception as e:
            logger.error(f"Error procesando refund: {e}")
            raise WebhookProcessingError(f"Failed to process refund: {e}")
    
    # Evento no reconocido o que no requiere acción
    logger.info(
        f"Webhook {provider_name} ignorado (no requiere acción): {normalized.event_type}"
    )
    
    return {
        "status": "ignored",
        "event": normalized.event_type,
        "message": "Event type does not require action",
    }


__all__ = [
    "handle_webhook",
    "WebhookSignatureError",
    "WebhookProcessingError",
]

# Fin del archivo
