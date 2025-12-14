# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/login_failure_reason_enum.py

Enum de razones de falla en intentos de login.
Usado como tipo ENUM en PostgreSQL (login_failure_reason_enum).

Razones: invalid_credentials, user_not_found, account_locked, account_not_activated, 
too_many_attempts, password_reset_required

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""
from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

class LoginFailureReason(StrEnum):
    """Razones de falla en el login"""
    invalid_credentials = "invalid_credentials"
    user_not_found = "user_not_found"
    account_locked = "account_locked"
    account_not_activated = "account_not_activated"
    too_many_attempts = "too_many_attempts"
    password_reset_required = "password_reset_required"

def as_pg_enum(
    name: str = "login_failure_reason_enum",
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
    return PG_ENUM(LoginFailureReason, name=name, create_type=create_type)

__all__ = ["LoginFailureReason", "as_pg_enum"]

# Fin del archivo backend/app/modules/auth/enums/login_failure_reason_enum.py

