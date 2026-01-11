# -*- coding: utf-8 -*-
"""
backend/app/shared/queries/wallet_balance.py

Helper para construcción del statement de balance de wallet.
Usado por ProfileService.get_credits_balance y tests.

SSOT para Wallet: importar desde app.modules.billing

Autor: DoxAI
Fecha: 2026-01-11
"""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.sql import Select


def build_wallet_balance_statement(auth_user_id: UUID, wallet_model=None) -> Select:
    """
    Construye el statement ORM para obtener balance de wallet.
    
    Args:
        auth_user_id: UUID del usuario
        wallet_model: Modelo Wallet (opcional, para evitar import circular).
                      Si es None, importa desde SSOT.
        
    Returns:
        Select statement listo para execute()
    """
    if wallet_model is None:
        # SSOT: billing.models no importa services/routers (evita circular)
        from app.modules.billing.models import Wallet
        wallet_model = Wallet
    
    return (
        select(wallet_model.balance)
        .where(wallet_model.auth_user_id == auth_user_id)
        .limit(1)
    )


def validate_wallet_statement(stmt: Select) -> dict:
    """
    Valida que un statement de wallet cumple los requisitos.
    
    Args:
        stmt: Statement SQLAlchemy a validar
        
    Returns:
        dict con resultados de validación
    """
    from sqlalchemy.dialects import postgresql
    
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql_str = str(compiled).lower()
    
    return {
        "has_balance_column": "balance" in sql_str,
        "has_auth_user_id_filter": "auth_user_id" in sql_str,
        "has_limit": "limit" in sql_str,
    }
