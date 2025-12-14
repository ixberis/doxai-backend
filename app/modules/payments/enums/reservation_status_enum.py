
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/enums/reservation_status_enum.py

Enum de estado de una reservación de créditos.
Sincronizado con el tipo ENUM de PostgreSQL: reservation_status_enum.

Autor: Ixchel Beristain
Fecha: 20/11/2025 (ajustado)
"""

from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

from app.shared.database.base import as_pg_enum as _as_pg_enum


class ReservationStatus(StrEnum):
    """Estado de una reservación de créditos."""

    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"

    __pg_enum_name__ = "reservation_status_enum"

    @classmethod
    def as_pg_enum(
        cls,
        name: str = "reservation_status_enum",
        schema: str | None = "public",
    ) -> PG_ENUM:
        return _as_pg_enum(cls, name=name, schema=schema)


def as_pg_enum(
    name: str = "reservation_status_enum",
    schema: str | None = "public",
) -> PG_ENUM:
    return ReservationStatus.as_pg_enum(name=name, schema=schema)


__all__ = ["ReservationStatus", "as_pg_enum"]

# Fin del archivo backend/app/modules/payments/enums/reservation_status_enum.py








