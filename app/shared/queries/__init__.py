# -*- coding: utf-8 -*-
"""
backend/app/shared/queries/__init__.py

Módulo de queries compartidas y helpers para construcción de statements.
Exporta constantes SQL y builders para facilitar testing sin parsing de source.

NOTA: Los imports son explícitos y mínimos para evitar errores de importación
en el path crítico de autenticación.

Autor: DoxAI
Fecha: 2026-01-11
"""

from .auth_lookup import (
    AUTH_LOOKUP_COLUMNS,
    AUTH_LOOKUP_SQL,
    build_auth_lookup_statement,
    validate_auth_lookup_sql,
)
from .wallet_balance import (
    build_wallet_balance_statement,
    validate_wallet_statement,
)

__all__ = [
    # Auth lookup
    "AUTH_LOOKUP_COLUMNS",
    "AUTH_LOOKUP_SQL",
    "build_auth_lookup_statement",
    "validate_auth_lookup_sql",
    # Wallet balance
    "build_wallet_balance_statement",
    "validate_wallet_statement",
]
