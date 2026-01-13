# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/email_types_enum.py

Tipos de emails de autenticación - fuente de verdad CANÓNICA.

Estos valores corresponden EXACTAMENTE al enum `auth_email_type` en Postgres.
SOLO valores canónicos, SIN aliases legacy:
  - activation
  - password_reset
  - password_reset_success
  - welcome
  - purchase_confirmation
  - admin_activation_notice

IMPORTANTE: El sistema RECHAZA valores legacy (account_activation, password_reset_request).

Autor: Sistema
Fecha: 2026-01-06
Updated: 2026-01-13 - ELIMINACIÓN TOTAL de aliases legacy
"""
from enum import StrEnum
from typing import Tuple


class AuthEmailType(StrEnum):
    """Enum con los tipos de email soportados (auth + billing + admin).
    
    IMPORTANTE: Estos valores DEBEN coincidir 1:1 con public.auth_email_type en SQL.
    
    Auth emails:
      - activation, password_reset, password_reset_success, welcome
    Billing emails:
      - purchase_confirmation
    Admin/Operativo:
      - admin_activation_notice (notificación al admin cuando usuario activa)
    """
    ACTIVATION = "activation"
    PASSWORD_RESET = "password_reset"
    PASSWORD_RESET_SUCCESS = "password_reset_success"
    WELCOME = "welcome"
    PURCHASE_CONFIRMATION = "purchase_confirmation"
    ADMIN_ACTIVATION_NOTICE = "admin_activation_notice"


# Tupla para uso directo en queries SQL (fuente de verdad centralizada)
AUTH_EMAIL_TYPES: Tuple[str, ...] = tuple(e.value for e in AuthEmailType)


# Set de valores legacy RECHAZADOS (existieron en producción, ahora prohibidos)
# - account_activation: usado en v1, reemplazado por 'activation'
# - password_reset_request: usado en v1, reemplazado por 'password_reset'
REJECTED_LEGACY_EMAIL_TYPES: frozenset[str] = frozenset({
    "account_activation",
    "password_reset_request",
})


def validate_email_type(email_type: str) -> str:
    """
    Valida que email_type sea un valor canónico SQL.
    
    RECHAZA valores legacy con error explícito.
    
    Args:
        email_type: Valor a validar (debe ser canónico)
        
    Returns:
        El mismo valor si es canónico
        
    Raises:
        ValueError: Si el valor es legacy o desconocido
        
    Examples:
        >>> validate_email_type("activation")
        'activation'
        >>> validate_email_type("account_activation")  # FALLA
        ValueError: Legacy email_type 'account_activation' rejected...
    """
    if email_type in REJECTED_LEGACY_EMAIL_TYPES:
        raise ValueError(
            f"Legacy email_type '{email_type}' rejected. "
            f"Use canonical value instead. Valid: {list(AUTH_EMAIL_TYPES)}"
        )
    
    if email_type not in AUTH_EMAIL_TYPES:
        raise ValueError(
            f"Invalid email_type '{email_type}'. "
            f"Valid values: {list(AUTH_EMAIL_TYPES)}"
        )
    
    return email_type


__all__ = [
    "AuthEmailType",
    "AUTH_EMAIL_TYPES",
    "REJECTED_LEGACY_EMAIL_TYPES",
    "validate_email_type",
]

# Fin del archivo
