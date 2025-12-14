
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/enums/credit_tx_type_enum.py

Enum de tipos de transacción de créditos.
Sincronizado con el tipo ENUM de PostgreSQL: credit_tx_type_enum.

Autor: Ixchel Beristain
Fecha: 20/11/2025 (ajustado)
"""

from enum import StrEnum
from typing import Iterable, Type

from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from app.shared.database.base import as_pg_enum as _as_pg_enum


class CreditTxType(StrEnum):
    """Tipo de movimiento en el ledger de créditos."""

    CREDIT = "credit"
    DEBIT = "debit"

    __pg_enum_name__ = "credit_tx_type_enum"

    @classmethod
    def as_pg_enum(
        cls,
        name: str = "credit_tx_type_enum",
        schema: str | None = "public",
    ) -> PG_ENUM:
        """Devuelve el tipo ENUM PostgreSQL para este enum."""
        return _as_pg_enum(cls, name=name, schema=schema)


def as_pg_enum(
    name: str = "credit_tx_type_enum",
    schema: str | None = "public",
) -> PG_ENUM:
    """
    Helper a nivel de módulo para compatibilidad.
    """
    return CreditTxType.as_pg_enum(name=name, schema=schema)


__all__ = ["CreditTxType", "as_pg_enum"]

# Fin del archivo backend\app\modules\payments\enums\credit_tx_type_enum.py







