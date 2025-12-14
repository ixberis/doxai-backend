
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/schemas/payment_status_schemas.py

Schemas para el endpoint de estado de pago (FASE 2 - UX Robusta).

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict


# Estados posibles como string literals para contrato estable con FE
PaymentStatusLiteral = Literal[
    "created",
    "pending",
    "authorized",
    "succeeded",
    "failed",
    "refunded",
    "cancelled",
]

# Estados que se consideran finales (no cambian más) - como strings
FINAL_STATUSES: frozenset[str] = frozenset({
    "succeeded",
    "failed",
    "refunded",
    "cancelled",
})


class PaymentStatusResponse(BaseModel):
    """
    Respuesta del endpoint de estado de pago para polling del Frontend.
    
    Contrato estable para FE:
    - is_final=False → seguir haciendo polling
    - is_final=True → estado definitivo, dejar de hacer polling
    - credits_awarded indica los créditos acreditados (solo si succeeded)
    - retry_after_seconds sugiere cuánto esperar antes del próximo poll
    - status es siempre string lowercase (created/pending/succeeded/failed/refunded/cancelled)
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    payment_id: int = Field(
        ...,
        description="ID único del pago."
    )
    
    status: str = Field(
        ...,
        description="Estado actual del pago (created/pending/authorized/succeeded/failed/refunded/cancelled)."
    )
    
    is_final: bool = Field(
        ...,
        description="True si el estado es definitivo (succeeded/failed/refunded/cancelled)."
    )
    
    credits_awarded: int = Field(
        default=0,
        ge=0,
        description="Créditos acreditados al usuario (solo si succeeded)."
    )
    
    webhook_verified_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp de verificación del webhook (null si aún no verificado)."
    )
    
    updated_at: datetime = Field(
        ...,
        description="Última actualización del pago."
    )
    
    retry_after_seconds: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Segundos sugeridos para esperar antes del próximo poll."
    )


__all__ = ["PaymentStatusResponse", "FINAL_STATUSES", "PaymentStatusLiteral"]

# Fin del archivo backend/app/modules/payments/schemas/payment_status_schemas.py

