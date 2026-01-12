# -*- coding: utf-8 -*-
"""
backend/app/routes/internal_db_checkout_intent_routes.py

Endpoint de diagnóstico para verificar configuración del modelo CheckoutIntent en runtime.

PATH: /_internal/db/checkout-intent-model
Método: GET
Protegido: INTERNAL_SERVICE_TOKEN + DB_MODEL_DIAGNOSTICS=1

Retorna:
- tablename: CheckoutIntent.__tablename__
- orm_columns: Lista de columnas del ORM mapper
- has_user_id: True si el ORM tiene user_id (ERROR - SSOT violation)
- has_auth_user_id: True si el ORM tiene auth_user_id (OK - SSOT requirement)
- db_columns: Columnas reales de checkout_intents en BD
- ssot_valid: True si pasa todas las validaciones
- build_version: GIT_SHA / RAILWAY_GIT_COMMIT_SHA / APP_VERSION

Autor: DoxAI
Fecha: 2026-01-12
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect

from app.shared.database.database import get_async_session
from app.shared.internal_auth import require_internal_service_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/db", tags=["internal-db-diagnostics"])

# Flag para habilitar/deshabilitar endpoint
_DIAGNOSTICS_ENABLED = os.getenv("DB_MODEL_DIAGNOSTICS", "0") == "1"

# Instancia de la dependencia de auth interna
_internal_auth = require_internal_service_token


def _get_build_version() -> str:
    """
    Get build/deploy version from environment.
    Priority: RAILWAY_GIT_COMMIT_SHA > GIT_SHA > APP_VERSION > "unknown"
    """
    return (
        os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_SHA")
        or os.getenv("APP_VERSION")
        or "unknown"
    )


@router.get("/checkout-intent-model")
async def get_checkout_intent_model_diagnostic(
    _: None = Depends(_internal_auth),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retorna diagnóstico completo del modelo CheckoutIntent para verificar SSOT.
    
    Requiere:
    - Header X-Internal-Service-Token
    - DB_MODEL_DIAGNOSTICS=1 (env var)
    
    Retorna 404 si DB_MODEL_DIAGNOSTICS=0 para evitar exposición.
    """
    if not _DIAGNOSTICS_ENABLED:
        raise HTTPException(status_code=404, detail="Diagnostics disabled")
    
    result = {
        "build_version": _get_build_version(),
        "tablename": None,
        "module": None,
        "orm_columns": [],
        "has_user_id": False,
        "has_auth_user_id": False,
        "db_columns": [],
        "db_has_user_id": False,
        "db_has_auth_user_id": False,
        "ssot_valid": False,
        "ssot_errors": [],
        "error": None,
    }
    
    try:
        from app.modules.billing.models import CheckoutIntent
        
        # Información del modelo
        result["tablename"] = getattr(CheckoutIntent, "__tablename__", "UNKNOWN")
        result["module"] = getattr(CheckoutIntent, "__module__", "UNKNOWN")
        
        # ORM mapper columns
        mapper = inspect(CheckoutIntent)
        orm_columns = [col.key for col in mapper.columns]
        result["orm_columns"] = orm_columns
        result["has_user_id"] = "user_id" in orm_columns
        result["has_auth_user_id"] = "auth_user_id" in orm_columns
        
        # DB columns from information_schema
        try:
            db_cols_result = await db.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'checkout_intents'
                ORDER BY ordinal_position
            """))
            db_columns = [row[0] for row in db_cols_result.fetchall()]
            result["db_columns"] = db_columns
            result["db_has_user_id"] = "user_id" in db_columns
            result["db_has_auth_user_id"] = "auth_user_id" in db_columns
        except Exception as e:
            result["db_columns"] = [f"error: {e}"]
        
        # Validate SSOT
        ssot_errors = []
        
        if result["tablename"] != "checkout_intents":
            ssot_errors.append(f"__tablename__='{result['tablename']}' (expected 'checkout_intents')")
        
        if result["has_user_id"]:
            ssot_errors.append("ORM has user_id column (SSOT VIOLATION - must be removed)")
        
        if not result["has_auth_user_id"]:
            ssot_errors.append("ORM missing auth_user_id column (SSOT REQUIREMENT)")
        
        if result["db_has_user_id"]:
            ssot_errors.append("DB has user_id column (should be removed or deprecated)")
        
        if not result["db_has_auth_user_id"]:
            ssot_errors.append("DB missing auth_user_id column (SSOT REQUIREMENT)")
        
        result["ssot_errors"] = ssot_errors
        result["ssot_valid"] = len(ssot_errors) == 0
        
        # Log for diagnostics
        logger.info(
            "[checkout_intent_diagnostic] build=%s tablename=%s orm_columns=%s "
            "has_user_id=%s has_auth_user_id=%s db_columns_count=%d "
            "db_has_user_id=%s db_has_auth_user_id=%s ssot_valid=%s",
            result["build_version"][:12] if len(result["build_version"]) > 12 else result["build_version"],
            result["tablename"],
            len(result["orm_columns"]),
            result["has_user_id"],
            result["has_auth_user_id"],
            len(result["db_columns"]) if isinstance(result["db_columns"], list) else 0,
            result["db_has_user_id"],
            result["db_has_auth_user_id"],
            result["ssot_valid"],
        )
        
        if not result["ssot_valid"]:
            logger.error(f"[checkout_intent_diagnostic] SSOT ERRORS: {ssot_errors}")
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[checkout_intent_diagnostic] Failed: {e}")
    
    return result


def log_checkout_intent_mapper_at_startup():
    """
    Log the CheckoutIntent mapper columns at startup for debugging.
    
    Call this from main.py lifespan to capture what SQLAlchemy will use for INSERT.
    """
    build_version = _get_build_version()
    
    try:
        from app.modules.billing.models import CheckoutIntent
        
        mapper = inspect(CheckoutIntent)
        orm_columns = sorted([col.key for col in mapper.columns])
        
        has_user_id = "user_id" in orm_columns
        has_auth_user_id = "auth_user_id" in orm_columns
        
        logger.info(
            "[startup_checkout_intent_mapper] build=%s tablename=%s columns=%s "
            "has_user_id=%s has_auth_user_id=%s SSOT_OK=%s",
            build_version[:12] if len(build_version) > 12 else build_version,
            CheckoutIntent.__tablename__,
            orm_columns,
            has_user_id,
            has_auth_user_id,
            has_auth_user_id and not has_user_id,
        )
        
        if has_user_id:
            logger.critical(
                "[startup_checkout_intent_mapper] CRITICAL: ORM contains user_id! "
                "This will cause INSERT failures. Build: %s",
                build_version,
            )
        
        if not has_auth_user_id:
            logger.critical(
                "[startup_checkout_intent_mapper] CRITICAL: ORM missing auth_user_id! "
                "This is a SSOT violation. Build: %s",
                build_version,
            )
        
    except Exception as e:
        logger.error(f"[startup_checkout_intent_mapper] Failed to inspect model: {e}")
