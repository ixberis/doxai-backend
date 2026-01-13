# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/email_types_enum.py

Tipos de emails de autenticación - fuente de verdad.

Estos valores corresponden EXACTAMENTE al enum `auth_email_type` en Postgres.
Canon único sin duplicados semánticos:
  - activation (NO account_activation)
  - password_reset (NO password_reset_request)
  - password_reset_success
  - welcome

Autor: Sistema
Fecha: 2026-01-06
Updated: 2026-01-13 - Alineación canónica con SQL (sin duplicados)
"""
from enum import StrEnum
from typing import Tuple


class AuthEmailType(StrEnum):
    """Enum con los tipos de email de autenticación soportados.
    
    IMPORTANTE: Estos valores DEBEN coincidir 1:1 con public.auth_email_type en SQL.
    """
    ACTIVATION = "activation"
    PASSWORD_RESET = "password_reset"
    PASSWORD_RESET_SUCCESS = "password_reset_success"
    WELCOME = "welcome"


# Tupla para uso directo en queries SQL (fuente de verdad centralizada)
AUTH_EMAIL_TYPES: Tuple[str, ...] = tuple(e.value for e in AuthEmailType)


# ─────────────────────────────────────────────────────────────────────────────
# Aliases para compatibilidad temporal (normalización a canon)
# Permite que código legacy use nombres antiguos sin romper
# ─────────────────────────────────────────────────────────────────────────────
EMAIL_TYPE_ALIASES: dict[str, str] = {
    # Legacy → Canon
    "account_activation": "activation",
    "password_reset_request": "password_reset",
    # Canon → Canon (pass-through)
    "activation": "activation",
    "password_reset": "password_reset",
    "password_reset_success": "password_reset_success",
    "welcome": "welcome",
}


def normalize_email_type(email_type: str) -> str:
    """
    Normaliza un email_type a su valor canónico SQL.
    
    Acepta aliases legacy y retorna el valor canónico para inserción en BD.
    
    Args:
        email_type: Valor original (puede ser alias o canónico)
        
    Returns:
        Valor canónico (activation, password_reset, etc.)
        
    Raises:
        ValueError: Si el valor no es reconocido
        
    Examples:
        >>> normalize_email_type("account_activation")
        'activation'
        >>> normalize_email_type("password_reset_request")
        'password_reset'
        >>> normalize_email_type("activation")
        'activation'
    """
    canonical = EMAIL_TYPE_ALIASES.get(email_type)
    if canonical is None:
        raise ValueError(
            f"Invalid email_type '{email_type}'. "
            f"Valid values: {list(EMAIL_TYPE_ALIASES.keys())}"
        )
    return canonical


__all__ = [
    "AuthEmailType",
    "AUTH_EMAIL_TYPES",
    "EMAIL_TYPE_ALIASES",
    "normalize_email_type",
]

# Fin del archivo
