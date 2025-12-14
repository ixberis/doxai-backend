
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/enums/payment_status_enum.py

Enum de estados del pago.
Sincronizado con el tipo ENUM de PostgreSQL: payment_status_enum.

Autor: Ixchel Beristain
Fecha: 20/11/2025 (ajustado)
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from app.shared.database.base import as_pg_enum as _as_pg_enum


class PaymentStatus(StrEnum):
    """Estado del pago en el ciclo de vida con el proveedor."""

    CREATED = "created"
    PENDING = "pending"
    AUTHORIZED = "authorized"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

    __pg_enum_name__ = "payment_status_enum"

    @classmethod
    def as_pg_enum(
        cls,
        name: str = "payment_status_enum",
        schema: str | None = "public",
    ) -> PG_ENUM:
        return _as_pg_enum(cls, name=name, schema=schema)


def as_pg_enum(
    name: str = "payment_status_enum",
    schema: str | None = "public",
) -> PG_ENUM:
    return PaymentStatus.as_pg_enum(name=name, schema=schema)


__all__ = ["PaymentStatus", "as_pg_enum"]

# Fin del archivo backend/app/modules/payments/enums/payment_status_enum.py









