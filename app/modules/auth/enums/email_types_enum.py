# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/email_types_enum.py

Tipos de emails de autenticación - fuente de verdad.

Estos valores corresponden al enum `auth_email_type` en Postgres y se usan
para filtrar métricas de entregabilidad en el agregador operativo.

Autor: Sistema
Fecha: 2026-01-06
"""
from enum import StrEnum
from typing import Tuple


class AuthEmailType(StrEnum):
    """Enum con los tipos de email de autenticación soportados."""
    ACCOUNT_ACTIVATION = "account_activation"
    ACCOUNT_CREATED = "account_created"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_SUCCESS = "password_reset_success"
    WELCOME = "welcome"


# Tupla para uso directo en queries SQL (fuente de verdad centralizada)
AUTH_EMAIL_TYPES: Tuple[str, ...] = tuple(e.value for e in AuthEmailType)


__all__ = [
    "AuthEmailType",
    "AUTH_EMAIL_TYPES",
]

# Fin del archivo
