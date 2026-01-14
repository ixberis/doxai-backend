# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/login_failure_reason_enum.py

Enum de razones de falla en intentos de login.
Usado como tipo ENUM en PostgreSQL (login_failure_reason_enum).

IMPORTANTE: Estos valores DEBEN coincidir exactamente con los valores
definidos en database/auth/01_types/01_auth_enums.sql (base) y
03_login_failure_reason_expand.sql (expansión):

Valores BASE (01_auth_enums.sql):
  - invalid_credentials
  - inactive_user
  - blocked_user
  - rate_limited

Valores EXPANDIDOS (03_login_failure_reason_expand.sql):
  - user_not_found
  - account_locked
  - account_not_activated
  - too_many_attempts
  - password_reset_required

Mappings para métricas (compatibilidad histórica):
  - Rate limit: too_many_attempts, rate_limited
  - Lockouts: account_locked, blocked_user

Autor: Ixchel Beristain
Fecha: 23/10/2025
Updated: 2026-01-14 - Expandido con valores canónicos adicionales
"""
from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class LoginFailureReason(StrEnum):
    """
    Razones de falla en el login.
    
    Valores alineados con login_failure_reason_enum en PostgreSQL.
    Incluye tanto valores legacy como nuevos canónicos.
    """
    # Base values (01_auth_enums.sql)
    invalid_credentials = "invalid_credentials"
    inactive_user = "inactive_user"
    blocked_user = "blocked_user"  # Legacy: mapped to account_locked in metrics
    rate_limited = "rate_limited"  # Legacy: mapped to too_many_attempts in metrics
    
    # Expanded values (03_login_failure_reason_expand.sql)
    user_not_found = "user_not_found"
    account_locked = "account_locked"
    account_not_activated = "account_not_activated"
    too_many_attempts = "too_many_attempts"
    password_reset_required = "password_reset_required"


# Canonical groupings for metrics (use these in aggregators)
RATE_LIMIT_REASONS = frozenset({
    LoginFailureReason.too_many_attempts.value,
    LoginFailureReason.rate_limited.value,  # Legacy
})

LOCKOUT_REASONS = frozenset({
    LoginFailureReason.account_locked.value,
    LoginFailureReason.blocked_user.value,  # Legacy
})


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


__all__ = [
    "LoginFailureReason",
    "RATE_LIMIT_REASONS",
    "LOCKOUT_REASONS",
    "as_pg_enum",
]

# Fin del archivo backend/app/modules/auth/enums/login_failure_reason_enum.py

