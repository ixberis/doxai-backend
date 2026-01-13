# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/__init__.py

Export central de enums de autenticación.

Punto de importación estable para todos los enums del módulo Auth:
- UserRole: roles de usuario (customer, admin, staff)
- UserStatus: estados del usuario en el sistema (active, cancelled, no_payment, not_active, suspended)
- ActivationStatus: estados de activación de cuenta (sent, used, expired, revoked)
- LoginFailureReason: razones de falla en login (invalid_credentials, user_not_found, etc.)
- TokenType: tipos de token JWT (access, activation, refresh, password_reset)
- AuthEmailType: tipos de email de autenticación (account_activation, welcome, etc.)
- AuthEmailEventStatus: estados de eventos de email (sent, delivered, bounced, etc.)

Todos los enums están mapeados 1:1 con tipos PostgreSQL ENUM que se crearán en la BD mediante Alembic.

Autor: Ixchel Beristain
Fecha: 23/10/2025
Actualizado: 2026-01-06 - Agregados enums de email types y event status
"""

# ===== AUTH =====
from .role_enum import UserRole, as_pg_enum as user_role_pg_enum
from .activation_status_enum import ActivationStatus, as_pg_enum as activation_status_pg_enum
from .user_status_enum import UserStatus, as_pg_enum as user_status_pg_enum
from .login_failure_reason_enum import LoginFailureReason, as_pg_enum as login_failure_reason_pg_enum
from .token_type_enum import TokenType, as_pg_enum as token_type_pg_enum

# ===== EMAIL =====
from .email_types_enum import AuthEmailType, AUTH_EMAIL_TYPES, EMAIL_TYPE_ALIASES, normalize_email_type
from .email_event_status_enum import (
    AuthEmailEventStatus,
    EMAIL_OPERATIONAL_STATUSES,
    EMAIL_DELIVERABILITY_STATUSES,
    ALL_EMAIL_EVENT_STATUSES,
    EMAIL_SENT_LIKE_STATUSES,
)

# ===== REGISTRY PARA ACCESO CENTRALIZADO =====
PG_ENUM_REGISTRY = {
    "user_role_enum": user_role_pg_enum,
    "activation_status_enum": activation_status_pg_enum,
    "user_status_enum": user_status_pg_enum,
    "login_failure_reason_enum": login_failure_reason_pg_enum,
    "token_type_enum": token_type_pg_enum,
}


def get_pg_enum(name: str, **kwargs):
    """
    Helper para acceso dinámico a enums PostgreSQL desde el registry.
    
    Args:
        name: Nombre del enum (clave en PG_ENUM_REGISTRY)
        **kwargs: Parámetros para la función as_pg_enum (create_type, native_enum, etc.)
    
    Returns:
        PG_ENUM configurado
    
    Raises:
        KeyError: Si el nombre no existe en el registry
    
    Example:
        >>> get_pg_enum("user_role_enum", create_type=True)
    """
    if name not in PG_ENUM_REGISTRY:
        raise KeyError(f"Enum '{name}' no encontrado en PG_ENUM_REGISTRY. Disponibles: {list(PG_ENUM_REGISTRY.keys())}")
    return PG_ENUM_REGISTRY[name](**kwargs)


__all__ = [
    # Auth Enums
    "UserRole",
    "ActivationStatus",
    "UserStatus",
    "LoginFailureReason",
    "TokenType",
    
    # Email Enums
    "AuthEmailType",
    "AUTH_EMAIL_TYPES",
    "EMAIL_TYPE_ALIASES",
    "normalize_email_type",
    "AuthEmailEventStatus",
    "EMAIL_OPERATIONAL_STATUSES",
    "EMAIL_DELIVERABILITY_STATUSES",
    "ALL_EMAIL_EVENT_STATUSES",
    "EMAIL_SENT_LIKE_STATUSES",

    # PG Enum Functions
    "user_role_pg_enum",
    "activation_status_pg_enum",
    "user_status_pg_enum",
    "login_failure_reason_pg_enum",
    "token_type_pg_enum",

    # Registry
    "PG_ENUM_REGISTRY",
    "get_pg_enum",
]

# Fin del archivo backend/app/modules/auth/enums/__init__.py
