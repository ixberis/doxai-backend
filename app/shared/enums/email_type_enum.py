
# -*- coding: utf-8 -*-
"""
backend/app/shared/enums/email_type_enum.py

Tipos de correo para sistema de créditos prepagados (DB-backed).
Usar en user_email_logs.email_type.

TAXONOMÍA Y PREFIJOS:
- Cuenta y autenticación: account_*, welcome, login_* (eventos de usuario final)
- reset_password_*: flujo de recuperación de contraseña
- profile_*: cambios de perfil de usuario
- payment_*: transacciones de recarga/top-up
- credits_*: eventos del ciclo de vida de créditos prepagados
- admin_*: alertas internas para equipo administrativo

El proveedor de pago se maneja en el payload/metadata del correo, no en el tipo.

Autor: Ixchel Beristain
Actualizado: 23/10/2025
"""

from enum import StrEnum
from typing import Any
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class EmailType(StrEnum):
    # === AUTENTICACIÓN Y CUENTA ===
    ACCOUNT_ACTIVATION = "account_activation"
    ACCOUNT_VERIFIED = "account_verified"
    WELCOME = "welcome"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGIN_CHALLENGE_REQUIRED = "login_challenge_required"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_DELETED = "account_deleted"
    
    # === RECUPERACIÓN DE CONTRASEÑA ===
    RESET_PASSWORD = "reset_password"
    RESET_PASSWORD_REQUEST = "reset_password_request"
    RESET_PASSWORD_SUCCESS = "reset_password_success"
    RESET_PASSWORD_FAILURE = "reset_password_failure"
    
    # === PERFIL ===
    PROFILE_UPDATED = "profile_updated"

    # === PAGOS - RECARGAS/TOP-UPS ===
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"

    # === CRÉDITOS PREPAGADOS ===
    CREDITS_ADDED = "credits_added"
    CREDITS_LOW_BALANCE = "credits_low_balance"
    CREDITS_DEPLETED = "credits_depleted"
    CREDITS_GRANT = "credits_grant"
    CREDITS_ADJUSTED = "credits_adjusted"

    # === ALERTAS ADMIN ===
    ADMIN_USER_ACTIVATED_ALERT = "admin_user_activated_alert"
    ADMIN_PAYMENT_ALERT = "admin_payment_alert"


def as_pg_enum(name: str = "email_type_enum", schema: str | None = None):
    from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
    pg = PG_ENUM(
        *[e.value for e in EmailType],  # ← valores posicionales (minúsculas)
        name=name,
        schema=schema,
        create_type=False,
    )
    pg.enum_class = EmailType
    return pg


__all__ = ["EmailType", "as_pg_enum"]
# Fin del script







