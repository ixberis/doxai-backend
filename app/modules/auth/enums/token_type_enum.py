# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/token_type_enum.py

Enum de tipos de token JWT.
Usado como tipo ENUM en PostgreSQL (token_type_enum).

Tipos: access, activation, refresh, password_reset

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""
from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

class TokenType(StrEnum):
    """Tipos de tokens JWT en el sistema"""
    access = "access"
    activation = "activation"
    refresh = "refresh"
    password_reset = "password_reset"

def as_pg_enum(
    name: str = "token_type_enum",
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
    return PG_ENUM(TokenType, name=name, create_type=create_type)

__all__ = ["TokenType", "as_pg_enum"]

# Fin del archivo backend/app/modules/auth/enums/token_type_enum.py

