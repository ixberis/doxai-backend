
# -*- coding: utf-8 -*-
"""
backend/app/shared/database/base.py

Base declarativa y convención de nombres para modelos ORM.

Este módulo proporciona:
- Base: clase base declarativa de SQLAlchemy
- NAMING_CONVENTION: convención de nombres para constraints
- as_pg_enum: helper genérico para mapear enums Python a ENUM de PostgreSQL

Autor: DoxAI
Fecha: 2025-10-18 (ajustado 2025-11-21)
"""

from __future__ import annotations

from enum import Enum
from typing import Type

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

# ===== NAMING CONVENTION =====
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# ===== BASE DECLARATIVA =====
class Base(DeclarativeBase):
    """
    Base declarativa para todos los modelos ORM de DoxAI.
    Incluye convención de nombres para constraints.
    """
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ===== HELPER GENÉRICO PARA ENUMS PG =====
def as_pg_enum(
    enum_cls: Type[Enum],
    name: str | None = None,
    schema: str | None = "public",
) -> PG_ENUM:
    """
    Devuelve un tipo ENUM de SQLAlchemy para PostgreSQL basado en un Enum de Python.

    Uso típico:

        from app.shared.database.base import Base, as_pg_enum
        from .enums import PaymentStatus

        class Payment(Base):
            status: Mapped[PaymentStatus] = mapped_column(
                as_pg_enum(PaymentStatus, name="payment_status_enum"),
                nullable=False,
            )

    - No crea el tipo en la BD (create_type=False): se asume que el ENUM
      ya existe creado vía scripts SQL.
    - Si no se pasa `name`, intenta usar `__pg_enum_name__` del enum,
      o el nombre de la clase en minúsculas.
    """
    enum_name = name or getattr(enum_cls, "__pg_enum_name__", enum_cls.__name__.lower())

    def _values(_: object) -> list[str]:
        return [e.value for e in enum_cls]  # type: ignore[arg-type]

    return PG_ENUM(
        enum_cls,
        name=enum_name,
        schema=schema,
        create_type=False,
        values_callable=_values,
    )


__all__ = ["Base", "NAMING_CONVENTION", "as_pg_enum"]

# Fin del archivo backend/app/shared/database/base.py
