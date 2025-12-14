
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/schemas/reservation_schemas.py

Esquemas para reservas de créditos (UsageReservation) en API v3.

Autor: Ixchel Beristain
Fecha: 2025-11-21 (v3)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.modules.payments.enums import ReservationStatus


class UsageReservationCreate(BaseModel):
    """
    Request para crear una reserva de créditos.

    La asociación a la wallet se hace por el usuario autenticado;
    no se expone wallet_id directamente en la API pública.
    """

    credits: int = Field(
        gt=0,
        description="Créditos a reservar temporalmente.",
    )
    ttl_minutes: int = Field(
        default=30,
        gt=0,
        le=24 * 60,
        description="Tiempo de vida de la reserva, en minutos.",
    )
    operation_id: Optional[str] = Field(
        default=None,
        description="ID idempotente opcional asociado a la operación.",
    )

    @field_validator("credits")
    @classmethod
    def validate_credits(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("credits must be > 0")
        return value


class UsageReservationOut(BaseModel):
    """
    Representación de una reserva de créditos.
    """

    id: int = Field(description="ID interno de la reserva.")
    status: ReservationStatus = Field(description="Estado actual de la reserva.")
    credits_reserved: int = Field(
        ge=0,
        description="Número de créditos reservados.",
    )
    operation_id: str = Field(
        description="ID idempotente asociado a esta reserva.",
    )
    expires_at: datetime = Field(
        description="Fecha/hora de expiración de la reserva.",
    )
    created_at: datetime = Field(description="Fecha/hora de creación.")
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Última fecha/hora de actualización.",
    )


__all__ = [
    "UsageReservationCreate",
    "UsageReservationOut",
]

# Fin del archivo backend/app/modules/payments/schemas/reservation_schemas.py
