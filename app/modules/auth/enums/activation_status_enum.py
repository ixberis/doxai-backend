# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/activation_status_enum.py

Enum de estados de activación de cuenta.
Usado como tipo ENUM en PostgreSQL (activation_status_enum).

Estados: sent, consumed, expired, revoked

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""
from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

class ActivationStatus(StrEnum):
    sent = "sent"
    consumed = "consumed"
    expired = "expired"
    revoked = "revoked"

def as_pg_enum(
    name: str = "activation_status_enum",
    *,
    create_type: bool = False):
    """
    Devuelve el tipo SQLAlchemy PG_ENUM para este enum,
    mapeado 1:1 al tipo que se creará en Postgres vía Alembic.
    
    Args:
        name: Nombre del tipo ENUM en PostgreSQL
        create_type: Si True, crea el tipo en DB (usar en bootstrap sin Alembic).
                     Si False, asume que el tipo ya existe (usar con migraciones).
    """
    return PG_ENUM(ActivationStatus, name=name, create_type=create_type)

__all__ = ["ActivationStatus", "as_pg_enum"]

# Fin del archivo backend/app/modules/auth/enums/activation_status_enum.py








