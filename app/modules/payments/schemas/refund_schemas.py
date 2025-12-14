
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/schemas/refund_schemas.py

Esquemas para reembolsos (Refund) en API v3.

Autor: Ixchel Beristain
Fecha: 2025-11-21 (v3)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.modules.payments.enums import Currency, RefundStatus


class RefundCreate(BaseModel):
    """
    Request para iniciar un reembolso manual desde la API.

    Este esquema se usará típicamente en endpoints administrativos.
    """

    payment_id: int = Field(description="ID del pago a reembolsar.")
    amount: Decimal = Field(
        gt=0,
        description="Monto a reembolsar en la moneda original del pago.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Motivo del reembolso (opcional, para auditoría).",
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be > 0")
        return value


class RefundOut(BaseModel):
    """
    Representación de un reembolso.
    """

    id: int = Field(description="ID interno del refund.")
    payment_id: int = Field(description="ID del pago asociado al refund.")
    currency: Currency = Field(
        description="Moneda del reembolso (igual a la del pago).",
    )
    amount: Decimal = Field(
        description="Monto reembolsado.",
    )
    credits_reversed: int = Field(
        ge=0,
        description="Créditos revertidos en el ledger a partir de este refund.",
    )
    status: RefundStatus = Field(
        description="Estado actual del refund.",
    )
    provider_refund_id: Optional[str] = Field(
        default=None,
        description="ID del refund en el proveedor externo.",
    )
    created_at: datetime = Field(description="Fecha/hora de creación.")
    updated_at: Optional[datetime] = Field(
        default=None, description="Última fecha/hora de actualización."
    )


__all__ = ["RefundCreate", "RefundOut"]

# Fin del archivo backend/app/modules/payments/schemas/refund_schemas.py

