# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/role_enum.py

Enum de roles de usuario.
Usado como tipo ENUM en PostgreSQL (user_role_enum).

Roles disponibles: customer, admin, staff

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""
from enum import StrEnum
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM

class UserRole(StrEnum):
    customer = "customer"
    admin = "admin"
    staff = "staff"

def as_pg_enum(
    name: str = "user_role_enum",
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
    return PG_ENUM(UserRole, name=name, create_type=create_type)

__all__ = ["UserRole", "as_pg_enum"]

# Fin del archivo backend/app/modules/auth/enums/role_enum.py








