
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/metrics_routes.py

Ruteador interno de métricas del módulo Auth.

Expone endpoints JSON de monitoreo interno:
- /_internal/auth/metrics/snapshot: refresca gauges derivados
  y devuelve un resumen de métricas seguras (sin PII).

Autor: Ixchel Beristain
Fecha: 2025-11-07
"""
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError

from app.shared.database.database import get_db
from app.modules.auth.metrics.schemas.metrics_schemas import AuthMetricsSnapshot
from app.modules.auth.metrics.exporters.prometheus_exporter import AuthPrometheusExporter

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
    
    Si las vistas SQL no existen, retorna 200 con campos null.
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_metrics_snapshot:{request_id}] Request started")
    
    active_sessions = None
    activation_ratio = None
    partial = False
    
    try:
        exp = AuthPrometheusExporter(db)
        
        # Try to get active sessions
        try:
            active_sessions = await exp.agg.get_active_sessions()
            logger.info(f"[auth_metrics_snapshot:{request_id}] active_sessions OK: {active_sessions}")
        except Exception as e:
            if _is_missing_view_error(e):
                logger.warning(f"[auth_metrics_snapshot:{request_id}] active_sessions: view missing")
            else:
                logger.exception(f"[auth_metrics_snapshot:{request_id}] active_sessions failed")
            partial = True
        
        # Try to get activation ratio (protected against division by zero in aggregator)
        try:
            activation_ratio = await exp.agg.get_latest_activation_conversion_ratio()
            # Protect against None or invalid values
            if activation_ratio is None or not isinstance(activation_ratio, (int, float)):
                activation_ratio = None
                partial = True
                logger.warning(f"[auth_metrics_snapshot:{request_id}] activation_ratio: null/invalid value")
            else:
                logger.info(f"[auth_metrics_snapshot:{request_id}] activation_ratio OK: {activation_ratio}")
        except Exception as e:
            if _is_missing_view_error(e):
                logger.warning(f"[auth_metrics_snapshot:{request_id}] activation_ratio: view missing")
            else:
                logger.exception(f"[auth_metrics_snapshot:{request_id}] activation_ratio failed")
            partial = True
        
        # Update Prometheus gauges only if values are available
        if active_sessions is not None:
            try:
                from app.modules.auth.metrics.collectors.auth_collectors import auth_active_sessions
                auth_active_sessions.set(active_sessions)
            except Exception:
                logger.warning(f"[auth_metrics_snapshot:{request_id}] Failed to update Prometheus gauge")
        
        if activation_ratio is not None:
            try:
                from app.modules.auth.metrics.collectors.auth_collectors import auth_activation_conversion_ratio
                auth_activation_conversion_ratio.set(activation_ratio)
            except Exception:
                logger.warning(f"[auth_metrics_snapshot:{request_id}] Failed to update Prometheus gauge")
        
        logger.info(f"[auth_metrics_snapshot:{request_id}] Request completed, partial={partial}")
        
        return AuthMetricsSnapshot(
            active_sessions=active_sessions,
            activation_conversion_ratio=activation_ratio,
            partial=partial,
        )
        
    except Exception as e:
        logger.exception(f"[auth_metrics_snapshot:{request_id}] fatal")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de autenticación",
        )


# Fin del archivo backend/app/modules/auth/metrics/routes/metrics_routes.py
