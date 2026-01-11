# -*- coding: utf-8 -*-
"""
backend/app/shared/queries/auth_lookup.py

Constantes y helpers para el lookup de autenticación por auth_user_id.
Usado por UserRepository.get_by_auth_user_id_core_ctx y tests.

Autor: DoxAI
Fecha: 2026-01-11
"""

from typing import List
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.sql import TextClause


# Columnas mínimas requeridas para AuthContextDTO
AUTH_LOOKUP_COLUMNS: List[str] = [
    "user_id",
    "auth_user_id",
    "user_email",
    "user_role",
    "user_status",
    "user_is_activated",
    "deleted_at",
]

# SQL canónico para auth lookup
# Predicado: auth_user_id = :auth_user_id AND deleted_at IS NULL
# Coincide con índice: idx_app_users_auth_user_id_not_deleted
AUTH_LOOKUP_SQL: str = """
    SELECT
        user_id,
        auth_user_id,
        user_email,
        user_role,
        user_status,
        user_is_activated,
        deleted_at
    FROM public.app_users
    WHERE auth_user_id = :auth_user_id
      AND deleted_at IS NULL
    LIMIT 1
"""


def build_auth_lookup_statement(auth_user_id: UUID) -> tuple[TextClause, dict]:
    """
    Construye el statement de auth lookup con parámetros.
    
    Args:
        auth_user_id: UUID del usuario a buscar
        
    Returns:
        Tupla (TextClause, params_dict) lista para execute()
    """
    return text(AUTH_LOOKUP_SQL.strip()), {"auth_user_id": auth_user_id}


# Validaciones estáticas (para tests)
def validate_auth_lookup_sql() -> dict:
    """
    Valida que el SQL de auth lookup cumple los requisitos.
    
    Returns:
        dict con resultados de validación
    """
    sql_lower = AUTH_LOOKUP_SQL.lower()
    
    return {
        "has_deleted_at_filter": "deleted_at is null" in sql_lower,
        "has_limit_1": "limit 1" in sql_lower,
        "has_auth_user_id_param": ":auth_user_id" in sql_lower,
        "column_count": len(AUTH_LOOKUP_COLUMNS),
        "excludes_password_hash": "password_hash" not in sql_lower,
    }
