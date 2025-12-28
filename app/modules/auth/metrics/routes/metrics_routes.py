
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/metrics_routes.py

Ruteador interno de métricas del módulo Auth v2 (DB-first).

Expone endpoints JSON de monitoreo interno:
- /_internal/auth/metrics/snapshot: 1 query a vista + sesiones

Estrategia:
- Intenta usar vista v_auth_metrics_snapshot_v2 (1 query)
- Si vista no existe, fallback a métodos individuales
- Sesiones siempre se consultan por separado (tiempo real)

Autor: Ixchel Beristain
Fecha: 2025-11-07
Actualizado: 2025-12-28 - DB-first con vista v2
"""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.metrics.schemas.metrics_schemas import AuthMetricsSnapshot
from app.modules.auth.metrics.aggregators.auth_aggregators import AuthAggregators

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/auth/metrics", tags=["metrics-auth"])


@router.get("/snapshot", response_model=AuthMetricsSnapshot)
async def get_auth_metrics_snapshot(db: AsyncSession = Depends(get_db)):
    """
    Refresca gauges derivados y devuelve un snapshot JSON
    con métricas agregadas (seguras) para dashboard interno.
    
    Estrategia DB-first:
    - 1 query a vista v_auth_metrics_snapshot_v2 para users/payments/ratios
    - 1 query para sesiones activas (tiempo real)
    - Fallback a queries individuales si vista no existe
    
    Campos v2:
    - users_total, users_deleted_total, users_suspended_total, users_current_total
    - users_activated_total, auth_active_sessions_total
    - auth_activation_conversion_ratio, payments_conversion_ratio
    - payments_paying_users_total
    - partial, generated_at
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_metrics_snapshot:{request_id}] Request started")
    
    partial = False
    agg = AuthAggregators(db)
    
    try:
        # ─────────────────────────────────────────────────────────
        # 1) Intentar vista v2 (1 query para todo users/payments)
        # ─────────────────────────────────────────────────────────
        v2_snapshot = await agg.get_auth_metrics_snapshot_v2()
        
        if v2_snapshot:
            users_total = v2_snapshot.users_total
            users_deleted_total = v2_snapshot.users_deleted_total
            users_suspended_total = v2_snapshot.users_suspended_total
            users_current_total = v2_snapshot.users_current_total
            users_activated_total = v2_snapshot.users_activated_total
            payments_paying_users_total = v2_snapshot.payments_paying_users_total
            auth_activation_conversion_ratio = v2_snapshot.auth_activation_conversion_ratio
            payments_conversion_ratio = v2_snapshot.payments_conversion_ratio
            
            # generated_at:
            # - DB timestamp when v_auth_metrics_snapshot_v2 is available
            # - Backend timestamp only in fallback mode
            generated_at = v2_snapshot.generated_at
            
            logger.info(
                f"[auth_metrics_snapshot:{request_id}] source=db_view "
                f"users_total={users_total} users_current={users_current_total} "
                f"deleted={users_deleted_total} suspended={users_suspended_total} "
                f"activated={users_activated_total} paying={payments_paying_users_total} "
                f"activation_ratio={auth_activation_conversion_ratio:.4f} "
                f"payments_ratio={payments_conversion_ratio:.4f} "
                f"generated_at={generated_at}"
            )
        else:
            # ─────────────────────────────────────────────────────────
            # 2) Fallback: queries individuales (vista no disponible)
            # ─────────────────────────────────────────────────────────
            partial = True
            
            users_total = await agg.get_users_total()
            users_deleted_total = await agg.get_users_deleted_total()
            users_suspended_total = await agg.get_users_suspended_total()
            users_current_total = await agg.get_users_current_total()
            users_activated_total = await agg.get_users_activated_total()
            payments_paying_users_total = await agg.get_paying_users_total()
            
            # Calculate ratios with div/0 handling
            auth_activation_conversion_ratio = (
                users_activated_total / users_total if users_total > 0 else 0.0
            )
            payments_conversion_ratio = (
                payments_paying_users_total / users_activated_total 
                if users_activated_total > 0 else 0.0
            )
            
            # Fallback: generar timestamp en backend (vista no disponible)
            generated_at = datetime.now(timezone.utc).isoformat()
            
            logger.warning(
                f"[auth_metrics_snapshot:{request_id}] source=fallback "
                f"users_total={users_total} users_current={users_current_total} "
                f"generated_at={generated_at}"
            )
        
        # ─────────────────────────────────────────────────────────
        # 3) Sesiones activas (siempre query separada, tiempo real)
        # ─────────────────────────────────────────────────────────
        auth_active_sessions_total = await agg.get_active_sessions()
        logger.info(f"[auth_metrics_snapshot:{request_id}] sessions={auth_active_sessions_total}")
        
        # ─────────────────────────────────────────────────────────
        # 4) Update Prometheus gauges (if available)
        # ─────────────────────────────────────────────────────────
        try:
            from app.modules.auth.metrics.collectors.auth_collectors import (
                auth_active_sessions,
                auth_activation_conversion_ratio as prometheus_ratio
            )
            auth_active_sessions.set(auth_active_sessions_total)
            prometheus_ratio.set(auth_activation_conversion_ratio)
        except Exception:
            logger.debug(f"[auth_metrics_snapshot:{request_id}] Prometheus gauges not available")
        
        # ─────────────────────────────────────────────────────────
        # 5) Build response
        # ─────────────────────────────────────────────────────────
        logger.info(f"[auth_metrics_snapshot:{request_id}] completed partial={partial}")
        
        return AuthMetricsSnapshot(
            users_total=users_total,
            users_deleted_total=users_deleted_total,
            users_suspended_total=users_suspended_total,
            users_current_total=users_current_total,
            users_activated_total=users_activated_total,
            auth_active_sessions_total=auth_active_sessions_total,
            auth_activation_conversion_ratio=auth_activation_conversion_ratio,
            payments_paying_users_total=payments_paying_users_total,
            payments_conversion_ratio=payments_conversion_ratio,
            partial=partial,
            generated_at=generated_at,
            # Legacy aliases (deprecated)
            active_sessions=auth_active_sessions_total,
            activation_conversion_ratio=auth_activation_conversion_ratio,
        )
        
    except Exception as e:
        logger.exception(f"[auth_metrics_snapshot:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de autenticación",
        )


