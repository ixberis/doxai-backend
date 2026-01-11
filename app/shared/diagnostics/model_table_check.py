# -*- coding: utf-8 -*-
"""
backend/app/shared/diagnostics/model_table_check.py

Diagnóstico de configuración del modelo Wallet vs tabla real en BD.

Uso: Activar con DB_MODEL_DIAGNOSTICS=1 en variables de entorno.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_MODEL_CHECK_DONE = False


async def run_wallet_table_diagnostic(db: "AsyncSession") -> None:
    """
    Verifica que la tabla configurada en Wallet coincide con BD.
    Ejecuta una sola vez por proceso.
    """
    global _MODEL_CHECK_DONE
    
    if _MODEL_CHECK_DONE:
        return
    
    if os.getenv("DB_MODEL_DIAGNOSTICS", "0") != "1":
        return
    
    _MODEL_CHECK_DONE = True
    
    try:
        from sqlalchemy import text
        from app.modules.billing.models import Wallet
        
        model_tablename = getattr(Wallet, "__tablename__", "UNKNOWN")
        
        result = await db.execute(text("""
            SELECT to_regclass('public.wallets') IS NOT NULL AS wallets_exists
        """))
        row = result.first()
        
        if row:
            wallets_exists = row[0]
            
            logger.info(
                f"[model_diagnostic] Wallet.__tablename__='{model_tablename}' | "
                f"DB: public.wallets={'EXISTS' if wallets_exists else 'NOT_FOUND'}"
            )
            
            if model_tablename != "wallets":
                logger.error(
                    f"[model_diagnostic] CRITICAL: Wallet.__tablename__='{model_tablename}' "
                    f"but BD 2.0 requires 'wallets'"
                )
            
            if not wallets_exists:
                logger.error(
                    "[model_diagnostic] CRITICAL: Table public.wallets does not exist"
                )
                
    except Exception as e:
        logger.warning(f"[model_diagnostic] Check failed (non-fatal): {e}")


def log_wallet_model_config() -> None:
    """Log de configuración del modelo sin conexión a BD."""
    if os.getenv("DB_MODEL_DIAGNOSTICS", "0") != "1":
        return
    
    try:
        from app.modules.billing.models import Wallet
        
        tablename = getattr(Wallet, "__tablename__", "UNKNOWN")
        logger.info(f"[model_config] Wallet.__tablename__ = '{tablename}'")
        
        if tablename != "wallets":
            logger.error(
                f"[model_config] INVALID: Expected 'wallets', got '{tablename}'"
            )
    except ImportError as e:
        logger.warning(f"[model_config] Could not import Wallet model: {e}")


__all__ = ["run_wallet_table_diagnostic", "log_wallet_model_config"]
