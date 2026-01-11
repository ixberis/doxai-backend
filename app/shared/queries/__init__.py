# -*- coding: utf-8 -*-
"""
backend/app/shared/queries/__init__.py

Módulo de queries compartidas y helpers para construcción de statements.
Exporta constantes SQL y builders para facilitar testing sin parsing de source.

Autor: DoxAI
Fecha: 2026-01-11
"""

from .auth_lookup import (
    AUTH_LOOKUP_SQL,
    AUTH_LOOKUP_COLUMNS,
    build_auth_lookup_statement,
)
from .wallet_balance import (
    build_wallet_balance_statement,
)

__all__ = [
    "AUTH_LOOKUP_SQL",
    "AUTH_LOOKUP_COLUMNS",
    "build_auth_lookup_statement",
    "build_wallet_balance_statement",
]
