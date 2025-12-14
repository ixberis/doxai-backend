
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/payment_event_service.py

Servicio para registrar y consultar eventos de pago
provenientes de webhooks (Stripe / PayPal).

FASE 3: Incluye sanitización de payloads antes de persistir.

Autor: Ixchel Beristain
Fecha: 2025-11-20 (actualizado 2025-12-13)
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.repositories.payment_event_repository import (
    PaymentEventRepository,
)
from app.modules.payments.services.webhooks.payload_sanitizer import (
    sanitize_webhook_payload,
)

if TYPE_CHECKING:
    from app.modules.payments.models.payment_event_models import PaymentEvent


class PaymentEventService:
    """
    Encapsula la lógica de idempotencia de eventos provenientes
    de pasarelas de pago.
    
    FASE 3: Sanitiza payloads antes de persistir para eliminar PII.
    """

    def __init__(self, event_repo: PaymentEventRepository) -> None:
        self.event_repo = event_repo

    # ---------------------------------------------------------
    # Registrar evento idempotente
    # ---------------------------------------------------------
    async def register_event(
        self,
        session: AsyncSession,
        *,
        payment_id: int,
        provider_event_id: str,
        event_type: str,
        payload: dict | None = None,
        provider: str = "unknown",
        raw_payload: bytes | None = None,
    ) -> "PaymentEvent":
        """
        Registra un evento. Si ya existe ese provider_event_id,
        regresa el existente (idempotente).
        
        FASE 3: El payload se sanitiza antes de guardar para eliminar PII.
        
        Args:
            session: Sesión de base de datos
            payment_id: ID del pago asociado
            provider_event_id: ID único del evento del proveedor
            event_type: Tipo de evento (checkout.completed, etc.)
            payload: Payload del webhook (se sanitizará)
            provider: Nombre del proveedor (stripe/paypal)
            raw_payload: Payload original en bytes (para hash)
        
        Returns:
            Evento registrado o existente
        """
        existing = await self.event_repo.get_by_provider_event_id(
            session, provider_event_id
        )
        if existing:
            return existing

        # FASE 3: Sanitizar payload antes de persistir
        sanitized_payload = {}
        if payload:
            sanitized_payload = sanitize_webhook_payload(
                provider=provider,
                payload=payload,
                include_hash=True,
                raw_payload=raw_payload,
            )

        event = await self.event_repo.create(
            session,
            payment_id=payment_id,
            provider_event_id=provider_event_id,
            event_type=event_type,
            payload_json=sanitized_payload,
        )
        return event

    async def get_by_provider_event_id(
        self,
        session: AsyncSession,
        provider_event_id: str,
    ) -> Optional["PaymentEvent"]:
        return await self.event_repo.get_by_provider_event_id(
            session, provider_event_id
        )
    

# Fin del archivo backend/app/modules/payments/services/payment_event_service.py
