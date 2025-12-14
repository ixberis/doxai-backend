
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/enums/currency_enum.py

Enum de monedas operativas del módulo Payments.
Sincronizado con el tipo ENUM de PostgreSQL: currency_enum.

Autor: Ixchel Beristain
Fecha: 20/11/2025 (ajustado)
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from app.shared.database.base import as_pg_enum as _as_pg_enum


class Currency(StrEnum):
    """Moneda operativa para cobros."""

    MXN = "mxn"
    USD = "usd"

    __pg_enum_name__ = "currency_enum"

    @classmethod
    def as_pg_enum(
        cls,
        name: str = "currency_enum",
        schema: str | None = "public",
    ) -> PG_ENUM:
        return _as_pg_enum(cls, name=name, schema=schema)


def as_pg_enum(
    name: str = "currency_enum",
    schema: str | None = "public",
) -> PG_ENUM:
    return Currency.as_pg_enum(name=name, schema=schema)


__all__ = ["Currency", "as_pg_enum"]

# Fin del archivo backend/app/modules/payments/enums/currency_enum.py







