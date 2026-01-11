# -*- coding: utf-8 -*-
"""
backend/app/routes/internal_db_wallet_routes.py

Endpoint de diagnóstico para verificar configuración del modelo Wallet en runtime.

PATH: /_internal/db/wallet-model
Método: GET
Protegido: INTERNAL_SERVICE_TOKEN + DB_MODEL_DIAGNOSTICS=1

Retorna:
- tablename: Wallet.__tablename__
- table_name: Wallet.__table__.name
- table_fullname: Wallet.__table__.fullname (si disponible)
- module: Wallet.__module__
- compiled_sql: SQL compilado del statement de balance
- table_wallets_exists: to_regclass('public.wallets')
- table_payments_wallet_exists: to_regclass('public.payments_wallet')
- ssot_valid: True si pasa todas las validaciones

Autor: DoxAI
Fecha: 2026-01-11
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects import postgresql

from app.shared.database.database import get_async_session
from app.modules.auth.dependencies import require_internal_service_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/db", tags=["internal-db-diagnostics"])

InternalServiceAuth = Depends(require_internal_service_token)

# Flag para habilitar/deshabilitar endpoint
_DIAGNOSTICS_ENABLED = os.getenv("DB_MODEL_DIAGNOSTICS", "0") == "1"


@router.get("/wallet-model")
async def get_wallet_model_diagnostic(
    _auth: None = InternalServiceAuth,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retorna diagnóstico completo del modelo Wallet para verificar SSOT.
    
    Requiere:
    - Header X-Internal-Service-Token
    - DB_MODEL_DIAGNOSTICS=1 (env var)
    
    Retorna 404 si DB_MODEL_DIAGNOSTICS=0 para evitar exposición.
    """
    if not _DIAGNOSTICS_ENABLED:
        raise HTTPException(status_code=404, detail="Diagnostics disabled")
    
    result = {
        "tablename": None,
        "table_name": None,
        "table_fullname": None,
        "module": None,
        "compiled_sql": None,
        "table_wallets_exists": None,
        "table_payments_wallet_exists": None,
        "ssot_valid": False,
        "ssot_errors": [],
        "error": None,
    }
    
    try:
        from app.modules.billing.models import Wallet
        from app.shared.queries.wallet_balance import build_wallet_balance_statement
        
        # Información del modelo
        result["tablename"] = getattr(Wallet, "__tablename__", "UNKNOWN")
        result["module"] = getattr(Wallet, "__module__", "UNKNOWN")
        
        # Table metadata (si existe __table__, modelo ya compilado)
        if hasattr(Wallet, "__table__"):
            table_obj = Wallet.__table__
            result["table_name"] = getattr(table_obj, "name", None)
            result["table_fullname"] = str(table_obj.fullname) if hasattr(table_obj, "fullname") else None
        
        # Compilar SQL
        test_uuid = uuid4()
        stmt = build_wallet_balance_statement(test_uuid, Wallet)
        compiled = stmt.compile(dialect=postgresql.dialect())
        result["compiled_sql"] = str(compiled)
        
        # Verificar existencia de AMBAS tablas en BD
        try:
            check_wallets = await db.execute(text(
                "SELECT to_regclass('public.wallets') IS NOT NULL AS exists"
            ))
            row = check_wallets.first()
            result["table_wallets_exists"] = row[0] if row else False
        except Exception as e:
            result["table_wallets_exists"] = f"error: {e}"
        
        try:
            check_legacy = await db.execute(text(
                "SELECT to_regclass('public.payments_wallet') IS NOT NULL AS exists"
            ))
            row = check_legacy.first()
            result["table_payments_wallet_exists"] = row[0] if row else False
        except Exception as e:
            result["table_payments_wallet_exists"] = f"error: {e}"
        
        # Validar SSOT (3 checks)
        ssot_errors = []
        
        if result["tablename"] != "wallets":
            ssot_errors.append(f"__tablename__='{result['tablename']}' (expected 'wallets')")
        
        if result["table_name"] is not None and result["table_name"] != "wallets":
            ssot_errors.append(f"__table__.name='{result['table_name']}' (expected 'wallets')")
        
        if result["table_fullname"] and "payments_wallet" in result["table_fullname"].lower():
            ssot_errors.append(f"__table__.fullname contains 'payments_wallet'")
        
        compiled_sql_lower = result["compiled_sql"].lower()
        if "payments_wallet" in compiled_sql_lower:
            ssot_errors.append("compiled_sql contains 'payments_wallet'")
        
        if "wallets" not in compiled_sql_lower:
            ssot_errors.append("compiled_sql does NOT contain 'wallets'")
        
        result["ssot_errors"] = ssot_errors
        result["ssot_valid"] = len(ssot_errors) == 0
        
        # Log para diagnóstico
        logger.info(
            f"[wallet_diagnostic] tablename={result['tablename']} "
            f"table_name={result['table_name']} "
            f"fullname={result['table_fullname']} "
            f"ssot_valid={result['ssot_valid']} "
            f"table_wallets_exists={result['table_wallets_exists']} "
            f"table_payments_wallet_exists={result['table_payments_wallet_exists']}"
        )
        
        if not result["ssot_valid"]:
            logger.error(f"[wallet_diagnostic] SSOT ERRORS: {ssot_errors}")
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[wallet_diagnostic] Failed: {e}")
    
    return result
