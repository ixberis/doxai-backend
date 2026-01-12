# -*- coding: utf-8 -*-
"""
backend/app/shared/queries/login_lookup.py

Constantes y helpers para el lookup de login optimizado.
Contiene SQL canónico para:
1. Lookup por email (full, para cache miss)
2. Lookup por user_id (para obtener password_hash después de cache hit)

NOTA: Este módulo debe ser "pure + lightweight" - sin imports pesados
que puedan romper el path de autenticación.

Autor: DoxAI
Fecha: 2026-01-12
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple

from sqlalchemy import text

if TYPE_CHECKING:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# SQL para lookup por email (cache MISS path)
# ─────────────────────────────────────────────────────────────────────────────

LOGIN_LOOKUP_BY_EMAIL_SQL: str = """
    SELECT
        user_id,
        auth_user_id,
        user_email,
        user_password_hash,
        user_role,
        user_status,
        user_is_activated,
        deleted_at,
        user_full_name
    FROM public.app_users
    WHERE user_email = :email
      AND deleted_at IS NULL
    LIMIT 1
"""


# ─────────────────────────────────────────────────────────────────────────────
# SQL para lookup de password_hash por user_id (cache HIT path)
# Solo trae password_hash - mínimo absoluto
# ─────────────────────────────────────────────────────────────────────────────

LOGIN_PASSWORD_HASH_BY_ID_SQL: str = """
    SELECT user_password_hash
    FROM public.app_users
    WHERE user_id = :user_id
      AND deleted_at IS NULL
    LIMIT 1
"""


def build_login_lookup_by_email(email: str) -> Tuple[Any, dict]:
    """
    Construye el statement de login lookup por email con parámetros.
    
    Args:
        email: Email normalizado (lower/strip) del usuario
        
    Returns:
        Tupla (TextClause, params_dict) lista para execute()
    """
    return text(LOGIN_LOOKUP_BY_EMAIL_SQL.strip()), {"email": email}


def build_password_hash_lookup(user_id: int) -> Tuple[Any, dict]:
    """
    Construye el statement de password hash lookup por user_id.
    
    Args:
        user_id: PK del usuario (INT)
        
    Returns:
        Tupla (TextClause, params_dict) lista para execute()
    """
    return text(LOGIN_PASSWORD_HASH_BY_ID_SQL.strip()), {"user_id": user_id}


# Validaciones estáticas (para tests)
def validate_login_lookup_sql() -> dict:
    """
    Valida que el SQL de login lookup cumple los requisitos.
    
    Returns:
        dict con resultados de validación
    """
    email_sql_lower = LOGIN_LOOKUP_BY_EMAIL_SQL.lower()
    pk_sql_lower = LOGIN_PASSWORD_HASH_BY_ID_SQL.lower()
    
    return {
        # Email lookup checks
        "email_has_deleted_at_filter": "deleted_at is null" in email_sql_lower,
        "email_has_limit_1": "limit 1" in email_sql_lower,
        "email_has_password_hash": "user_password_hash" in email_sql_lower,
        "email_has_auth_user_id": "auth_user_id" in email_sql_lower,
        # PK lookup checks
        "pk_has_deleted_at_filter": "deleted_at is null" in pk_sql_lower,
        "pk_has_limit_1": "limit 1" in pk_sql_lower,
        "pk_only_selects_password_hash": (
            "user_password_hash" in pk_sql_lower
            and "user_email" not in pk_sql_lower
        ),
    }


__all__ = [
    "LOGIN_LOOKUP_BY_EMAIL_SQL",
    "LOGIN_PASSWORD_HASH_BY_ID_SQL",
    "build_login_lookup_by_email",
    "build_password_hash_lookup",
    "validate_login_lookup_sql",
]
