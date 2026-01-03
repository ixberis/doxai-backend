
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/metrics_routes.py

Ruteador interno de métricas del módulo Auth v2 (DB-first).

Expone endpoints JSON de monitoreo interno:
- /_internal/auth/metrics/snapshot: 1 query a vista + sesiones (global)
- /_internal/auth/metrics/summary: métricas con rango de fechas (nuevo)

Estrategia:
- Intenta usar vista v_auth_metrics_snapshot_v2 (1 query)
- Si vista no existe, fallback a métodos individuales
- Sesiones siempre se consultan por separado (tiempo real)

Autor: Ixchel Beristain
Fecha: 2025-11-07
Actualizado: 2025-12-28 - DB-first con vista v2
Actualizado: 2026-01-02 - Nuevo endpoint summary con rango
"""
import logging
import uuid
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.metrics.schemas.metrics_schemas import (
    AuthMetricsSnapshot,
    AuthSummaryMetrics,
    AuthSummaryRange,
)
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
        #    Multi-sesión: retorna sessions, users, avg
        # ─────────────────────────────────────────────────────────
        active_sessions, active_users, sessions_avg = await agg.get_active_sessions_stats()
        logger.info(
            f"[auth_metrics_snapshot:{request_id}] sessions={active_sessions} "
            f"active_users={active_users} avg={sessions_avg:.2f}"
        )
        
        # ─────────────────────────────────────────────────────────
        # 4) Update Prometheus gauges (if available)
        # ─────────────────────────────────────────────────────────
        try:
            from app.modules.auth.metrics.collectors.auth_collectors import (
                auth_active_sessions,
                auth_activation_conversion_ratio as prometheus_ratio
            )
            auth_active_sessions.set(active_sessions)
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
            auth_active_sessions_total=active_sessions,
            auth_active_users_total=active_users,
            auth_sessions_per_user_avg=sessions_avg,
            auth_activation_conversion_ratio=auth_activation_conversion_ratio,
            payments_paying_users_total=payments_paying_users_total,
            payments_conversion_ratio=payments_conversion_ratio,
            partial=partial,
            generated_at=generated_at,
            # Legacy aliases (deprecated)
            active_sessions=active_sessions,
            activation_conversion_ratio=auth_activation_conversion_ratio,
        )
        
    except Exception as e:
        logger.exception(f"[auth_metrics_snapshot:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de autenticación",
        )


def _parse_date(date_str: str, param_name: str) -> date:
    """Parse and validate date string (YYYY-MM-DD)."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Parámetro '{param_name}' inválido. Formato esperado: YYYY-MM-DD"
        )


@router.get("/summary", response_model=AuthSummaryMetrics)
async def get_auth_metrics_summary(
    from_date: str = Query(..., alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(..., alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna métricas de Auth Funcional para un rango de fechas.
    
    Query params:
    - from: Fecha inicio (YYYY-MM-DD) - inclusive
    - to: Fecha fin (YYYY-MM-DD) - inclusive
    
    Returns:
    - users_created: usuarios registrados en el rango
    - users_activated: usuarios que activaron cuenta en el rango
    - users_paying: usuarios con ≥1 pago exitoso en el rango
    - creation_to_activation_ratio: users_activated / users_created
    - activation_to_payment_ratio: users_paying / users_activated
    - creation_to_payment_ratio: users_paying / users_created (NUEVO)
    - range: {from, to} 
    - generated_at: timestamp de generación
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_metrics_summary:{request_id}] from={from_date} to={to_date}")
    
    # Validar formato de fechas
    parsed_from = _parse_date(from_date, "from")
    parsed_to = _parse_date(to_date, "to")
    
    # Validar from <= to
    if parsed_from > parsed_to:
        raise HTTPException(
            status_code=400,
            detail="El parámetro 'from' debe ser anterior o igual a 'to'"
        )
    
    # Validar rango máximo (365 días)
    if (parsed_to - parsed_from).days > 365:
        raise HTTPException(
            status_code=400,
            detail="El rango máximo permitido es 365 días"
        )
    
    try:
        agg = AuthAggregators(db)
        summary = await agg.get_auth_summary(from_date, to_date)
        
        logger.info(
            f"[auth_metrics_summary:{request_id}] completed "
            f"users_created={summary.users_created} "
            f"users_activated={summary.users_activated} "
            f"users_paying={summary.users_paying}"
        )
        
        return AuthSummaryMetrics(
            range=AuthSummaryRange(
                from_date=summary.from_date,
                to_date=summary.to_date,
            ),
            users_created=summary.users_created,
            users_activated=summary.users_activated,
            users_paying=summary.users_paying,
            creation_to_activation_ratio=summary.creation_to_activation_ratio,
            activation_to_payment_ratio=summary.activation_to_payment_ratio,
            creation_to_payment_ratio=summary.creation_to_payment_ratio,
            generated_at=summary.generated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_metrics_summary:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular resumen de métricas",
        )

