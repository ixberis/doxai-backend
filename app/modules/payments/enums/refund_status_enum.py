
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/enums/refund_status_enum.py

Enum de estado del reembolso.
Sincronizado con el tipo ENUM de PostgreSQL: refund_status_enum.

Autor: Ixchel Beristain
Fecha: 20/11/2025 (ajustado)
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from app.shared.database.base import as_pg_enum as _as_pg_enum


class RefundStatus(StrEnum):
    """Estado del reembolso."""

    PENDING = "pending"
    REFUNDED = "refunded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    __pg_enum_name__ = "refund_status_enum"

    @classmethod
    def as_pg_enum(
        cls,
        name: str = "refund_status_enum",
        schema: str | None = "public",
    ) -> PG_ENUM:
        return _as_pg_enum(cls, name=name, schema=schema)


def as_pg_enum(
    name: str = "refund_status_enum",
    schema: str | None = "public",
) -> PG_ENUM:
    return RefundStatus.as_pg_enum(name=name, schema=schema)


__all__ = ["RefundStatus", "as_pg_enum"]

# Fin del archivo backend/app/modules/payments/enums/refund_status_enum.py