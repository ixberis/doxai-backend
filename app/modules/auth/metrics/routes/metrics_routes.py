
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/metrics_routes.py

Ruteador interno de métricas del módulo Auth.

Expone endpoints JSON de monitoreo interno:
- /_internal/auth/metrics/snapshot: refresca gauges derivados
  y devuelve un resumen de métricas seguras (sin PII).

Autor: Ixchel Beristain
Fecha: 2025-11-07
Actualizado: 2025-12-21 - Nuevas métricas definitivas
"""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError

from app.shared.database.database import get_db
from app.modules.auth.metrics.schemas.metrics_schemas import AuthMetricsSnapshot
from app.modules.auth.metrics.aggregators.auth_aggregators import AuthAggregators

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/auth/metrics", tags=["metrics-auth"])


def _is_missing_view_error(exc: Exception) -> bool:
    """Check if exception is due to missing SQL view/table."""
    error_msg = str(exc).lower()
    return (
        isinstance(exc, ProgrammingError) and 
        ("does not exist" in error_msg or "undefined_table" in error_msg)
    )


@router.get("/snapshot", response_model=AuthMetricsSnapshot)
async def get_auth_metrics_snapshot(db: AsyncSession = Depends(get_db)):
    """
    Refresca gauges derivados y devuelve un snapshot JSON
    con métricas agregadas (seguras) para dashboard interno.
    
    Implementa degradación parcial: si alguna métrica falla,
    devuelve null en ese campo y partial=True.
    
    Campos definitivos (v2):
    - users_total, users_activated_total
    - auth_active_sessions_total, auth_active_users_total
    - auth_activation_conversion_ratio
    - payments_paying_users_total
    - generated_at, partial
    
    Legacy aliases (deprecated):
    - active_sessions → auth_active_sessions_total
    - activation_conversion_ratio → auth_activation_conversion_ratio
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_metrics_snapshot:{request_id}] Request started")
    
    # Initialize all metrics as None
    users_total = None
    users_activated_total = None
    auth_active_sessions_total = None
    auth_active_users_total = None
    auth_activation_conversion_ratio = None
    payments_paying_users_total = None
    partial = False
    
    try:
        agg = AuthAggregators(db)
        
        # ─────────────────────────────────────────────────────────
        # Users metrics
        # ─────────────────────────────────────────────────────────
        try:
            users_total = await agg.get_users_total()
            logger.info(f"[auth_metrics_snapshot:{request_id}] users_total OK: {users_total}")
        except Exception as e:
            if _is_missing_view_error(e):
                logger.warning(f"[auth_metrics_snapshot:{request_id}] users_total: table missing")
            else:
                logger.exception(f"[auth_metrics_snapshot:{request_id}] users_total failed")
            partial = True
        
        try:
            users_activated_total = await agg.get_users_activated_total()
            logger.info(f"[auth_metrics_snapshot:{request_id}] users_activated_total OK: {users_activated_total}")
        except Exception as e:
            if _is_missing_view_error(e):
                logger.warning(f"[auth_metrics_snapshot:{request_id}] users_activated_total: table/column missing")
            else:
                logger.exception(f"[auth_metrics_snapshot:{request_id}] users_activated_total failed")
            partial = True
        
        # ─────────────────────────────────────────────────────────
        # Sessions metrics
        # ─────────────────────────────────────────────────────────
        try:
            auth_active_sessions_total = await agg.get_active_sessions()
            logger.info(f"[auth_metrics_snapshot:{request_id}] auth_active_sessions_total OK: {auth_active_sessions_total}")
        except Exception as e:
            if _is_missing_view_error(e):
                logger.warning(f"[auth_metrics_snapshot:{request_id}] auth_active_sessions_total: view missing")
            else:
                logger.exception(f"[auth_metrics_snapshot:{request_id}] auth_active_sessions_total failed")
            partial = True
        
        try:
            auth_active_users_total = await agg.get_active_users_total()
            logger.info(f"[auth_metrics_snapshot:{request_id}] auth_active_users_total OK: {auth_active_users_total}")
        except Exception as e:
            if _is_missing_view_error(e):
                logger.warning(f"[auth_metrics_snapshot:{request_id}] auth_active_users_total: view missing")
            else:
                logger.exception(f"[auth_metrics_snapshot:{request_id}] auth_active_users_total failed")
            partial = True
        
        # ─────────────────────────────────────────────────────────
        # Conversion metrics
        # ─────────────────────────────────────────────────────────
        try:
            # Try SQL function first
            auth_activation_conversion_ratio = await agg.get_latest_activation_conversion_ratio()
            
            # Fallback to calculated ratio if SQL function fails/returns null
            if auth_activation_conversion_ratio is None and users_total and users_total > 0:
                if users_activated_total is not None:
                    auth_activation_conversion_ratio = users_activated_total / users_total
            
            if auth_activation_conversion_ratio is not None:
                logger.info(f"[auth_metrics_snapshot:{request_id}] auth_activation_conversion_ratio OK: {auth_activation_conversion_ratio}")
            else:
                logger.warning(f"[auth_metrics_snapshot:{request_id}] auth_activation_conversion_ratio: null value")
                partial = True
        except Exception as e:
            if _is_missing_view_error(e):
                logger.warning(f"[auth_metrics_snapshot:{request_id}] auth_activation_conversion_ratio: view missing")
            else:
                logger.exception(f"[auth_metrics_snapshot:{request_id}] auth_activation_conversion_ratio failed")
            partial = True
        
        # ─────────────────────────────────────────────────────────
        # Payments metrics (graceful degradation if table doesn't exist)
        # ─────────────────────────────────────────────────────────
        try:
            payments_paying_users_total = await agg.get_paying_users_total()
            logger.info(f"[auth_metrics_snapshot:{request_id}] payments_paying_users_total OK: {payments_paying_users_total}")
        except Exception as e:
            if _is_missing_view_error(e):
                # Expected in environments without payments table
                logger.info(f"[auth_metrics_snapshot:{request_id}] payments_paying_users_total: table missing (expected)")
                payments_paying_users_total = None
            else:
                logger.exception(f"[auth_metrics_snapshot:{request_id}] payments_paying_users_total failed")
            partial = True
        
        # ─────────────────────────────────────────────────────────
        # Update Prometheus gauges (if available)
        # ─────────────────────────────────────────────────────────
        try:
            from app.modules.auth.metrics.collectors.auth_collectors import (
                auth_active_sessions,
                auth_activation_conversion_ratio as prometheus_ratio
            )
            if auth_active_sessions_total is not None:
                auth_active_sessions.set(auth_active_sessions_total)
            if auth_activation_conversion_ratio is not None:
                prometheus_ratio.set(auth_activation_conversion_ratio)
        except Exception:
            logger.warning(f"[auth_metrics_snapshot:{request_id}] Failed to update Prometheus gauges")
        
        # ─────────────────────────────────────────────────────────
        # Build response
        # ─────────────────────────────────────────────────────────
        generated_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(f"[auth_metrics_snapshot:{request_id}] Request completed, partial={partial}")
        
        return AuthMetricsSnapshot(
            # New definitive names
            users_total=users_total,
            users_activated_total=users_activated_total,
            auth_active_sessions_total=auth_active_sessions_total,
            auth_active_users_total=auth_active_users_total,
            auth_activation_conversion_ratio=auth_activation_conversion_ratio,
            payments_paying_users_total=payments_paying_users_total,
            partial=partial,
            generated_at=generated_at,
            # Legacy aliases (deprecated)
            active_sessions=auth_active_sessions_total,
            activation_conversion_ratio=auth_activation_conversion_ratio,
        )
        
    except Exception as e:
        logger.exception(f"[auth_metrics_snapshot:{request_id}] fatal")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de autenticación",
        )


# Fin del archivo backend/app/modules/auth/metrics/routes/metrics_routes.py
