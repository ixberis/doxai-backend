
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/enums/payment_provider_enum.py

Enum de proveedores de pago soportados.
Sincronizado con el tipo ENUM de PostgreSQL: payment_provider_enum.

Autor: Ixchel Beristain
Fecha: 20/11/2025 (ajustado)
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from app.shared.database.base import as_pg_enum as _as_pg_enum


class PaymentProvider(StrEnum):
    """Proveedor de pago externo."""

    STRIPE = "stripe"
    PAYPAL = "paypal"

    __pg_enum_name__ = "payment_provider_enum"

    @classmethod
    def as_pg_enum(
        cls,
        name: str = "payment_provider_enum",
        schema: str | None = "public",
    ) -> PG_ENUM:
        return _as_pg_enum(cls, name=name, schema=schema)


def as_pg_enum(
    name: str = "payment_provider_enum",
    schema: str | None = "public",
) -> PG_ENUM:
    return PaymentProvider.as_pg_enum(name=name, schema=schema)


__all__ = ["PaymentProvider", "as_pg_enum"]


# Fin del archivo backend/app/modules/payments/enums/payment_provider_enum.py








