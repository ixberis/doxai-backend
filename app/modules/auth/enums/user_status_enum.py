# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/user_status_enum.py

Enum de estados de usuario en el sistema.
Usado como tipo ENUM en PostgreSQL (user_status_enum).

Sistema de pago por uso con créditos prepagados.

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""
from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

class UserStatus(StrEnum):
    """Estados del usuario en el sistema (pago por uso con créditos)"""
    active = "active"
    cancelled = "cancelled"
    no_payment = "no_payment"
    not_active = "not_active"
    suspended = "suspended"

def as_pg_enum(
    name: str = "user_status_enum",
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
    return PG_ENUM(UserStatus, name=name, create_type=create_type)

__all__ = ["UserStatus", "as_pg_enum"]

# Fin del archivo backend/app/modules/auth/enums/user_status_enum.py

