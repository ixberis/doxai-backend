# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/operational_routes.py

Rutas para métricas operativas de Auth.

Endpoints:
- GET /_internal/auth/metrics/operational/summary
- GET /_internal/auth/metrics/operational/sessions
- GET /_internal/auth/metrics/operational/errors

Autor: Sistema
Fecha: 2026-01-03
"""
import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.metrics.schemas.operational_schemas import (
    OperationalSummaryResponse,
    SessionsDetailResponse,
    TopUserSessionsItem,
    ErrorsDetailResponse,
    LoginFailureByReasonItem,
)
from app.modules.auth.metrics.aggregators.operational_aggregators import (
    OperationalAggregators,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/_internal/auth/metrics/operational",
    tags=["metrics-auth-operational"],
)


def _parse_date(date_str: str, param_name: str) -> str:
    """Validate date format YYYY-MM-DD and return as-is."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Parámetro '{param_name}' inválido. Formato esperado: YYYY-MM-DD",
        )


def _validate_date_range(from_date: str, to_date: str) -> None:
    """Validate from <= to and max 365 days."""
    from_dt = datetime.strptime(from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(to_date, "%Y-%m-%d")
    
    if from_dt > to_dt:
        raise HTTPException(
            status_code=400,
            detail="El parámetro 'from' debe ser anterior o igual a 'to'",
        )
    
    if (to_dt - from_dt).days > 365:
        raise HTTPException(
            status_code=400,
            detail="El rango máximo permitido es 365 días",
        )


@router.get("/summary", response_model=OperationalSummaryResponse)
async def get_operational_summary(
    from_date: str = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Resumen operativo de Auth.
    
    - Sessions: siempre tiempo real (ignora rango)
    - Login attempts, emails: respetan rango
    - Rate limits, lockouts: respetan rango
    
    Query params:
    - from: Fecha inicio (YYYY-MM-DD) - opcional
    - to: Fecha fin (YYYY-MM-DD) - opcional
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_operational_summary:{request_id}] from={from_date} to={to_date}")
    
    # Validate dates if provided
    parsed_from = None
    parsed_to = None
    
    if from_date and to_date:
        parsed_from = _parse_date(from_date, "from")
        parsed_to = _parse_date(to_date, "to")
        _validate_date_range(parsed_from, parsed_to)
    elif from_date or to_date:
        # Both must be provided or neither
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar ambos parámetros 'from' y 'to', o ninguno",
        )
    
    try:
        agg = OperationalAggregators(db)
        data = await agg.get_operational_summary(parsed_from, parsed_to)
        
        # Log with source info for each metric
        logger.info(
            f"[auth_operational_summary:{request_id}] completed "
            f"source_sessions=function|direct "
            f"source_login_attempts=login_attempts "
            f"source_emails=auth_email_events "
            f"source_rate_limits=login_attempts(reason=too_many_attempts) "
            f"source_lockouts=login_attempts(reason=account_locked) "
            f"sessions={data.sessions_active_total} "
            f"login_attempts={data.login_attempts_total} "
            f"emails_sent={data.emails_sent_total}"
        )
        
        return OperationalSummaryResponse(
            sessions_active_total=data.sessions_active_total,
            sessions_active_users=data.sessions_active_users,
            sessions_per_user_avg=data.sessions_per_user_avg,
            login_attempts_total=data.login_attempts_total,
            login_attempts_failed=data.login_attempts_failed,
            login_failure_rate=data.login_failure_rate,
            rate_limit_triggers=data.rate_limit_triggers,
            lockouts_total=data.lockouts_total,
            emails_sent_total=data.emails_sent_total,
            emails_failed_total=data.emails_failed_total,
            email_failure_rate=data.email_failure_rate,
            period_from=data.period_from,
            period_to=data.period_to,
            generated_at=data.generated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_operational_summary:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas operativas",
        )


@router.get("/sessions", response_model=SessionsDetailResponse)
async def get_sessions_detail(
    from_date: str = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    limit: int = Query(10, ge=1, le=100, description="Límite de top users"),
    db: AsyncSession = Depends(get_db),
):
    """
    Detalle de sesiones.
    
    - Real-time: sesiones activas, usuarios, promedio
    - Period: sesiones creadas, expiradas, revocadas
    - Top users: ordenados por # sesiones activas
    
    Query params:
    - from: Fecha inicio (YYYY-MM-DD) - opcional
    - to: Fecha fin (YYYY-MM-DD) - opcional
    - limit: Límite de top users (default 10)
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_operational_sessions:{request_id}] from={from_date} to={to_date} limit={limit}")
    
    # Validate dates if provided
    parsed_from = None
    parsed_to = None
    
    if from_date and to_date:
        parsed_from = _parse_date(from_date, "from")
        parsed_to = _parse_date(to_date, "to")
        _validate_date_range(parsed_from, parsed_to)
    elif from_date or to_date:
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar ambos parámetros 'from' y 'to', o ninguno",
        )
    
    try:
        agg = OperationalAggregators(db)
        data = await agg.get_sessions_detail(parsed_from, parsed_to, limit)
        
        # Log with source info
        logger.info(
            f"[auth_operational_sessions:{request_id}] completed "
            f"source_sessions=function|direct "
            f"source_period=user_sessions "
            f"active={data.sessions_active_total} "
            f"created={data.sessions_created} "
            f"expired={data.sessions_expired} "
            f"revoked={data.sessions_revoked} "
            f"top_users={len(data.top_users)}"
        )
        
        return SessionsDetailResponse(
            sessions_active_total=data.sessions_active_total,
            sessions_active_users=data.sessions_active_users,
            sessions_per_user_avg=data.sessions_per_user_avg,
            sessions_created=data.sessions_created,
            sessions_expired=data.sessions_expired,
            sessions_revoked=data.sessions_revoked,
            top_users=[
                TopUserSessionsItem(
                    user_id=u.user_id,
                    user_email=u.user_email,
                    session_count=u.session_count,
                )
                for u in data.top_users
            ],
            period_from=data.period_from,
            period_to=data.period_to,
            generated_at=data.generated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_operational_sessions:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de sesiones",
        )


@router.get("/errors", response_model=ErrorsDetailResponse)
async def get_errors_detail(
    from_date: str = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Detalle de errores/fricción.
    
    - Login failures by reason
    - Rate limits by IP/user
    - Lockouts by IP/user
    - HTTP errors (not instrumented - siempre 0)
    
    Query params:
    - from: Fecha inicio (YYYY-MM-DD) - opcional
    - to: Fecha fin (YYYY-MM-DD) - opcional
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_operational_errors:{request_id}] from={from_date} to={to_date}")
    
    # Validate dates if provided
    parsed_from = None
    parsed_to = None
    
    if from_date and to_date:
        parsed_from = _parse_date(from_date, "from")
        parsed_to = _parse_date(to_date, "to")
        _validate_date_range(parsed_from, parsed_to)
    elif from_date or to_date:
        raise HTTPException(
            status_code=400,
            detail="Debe proporcionar ambos parámetros 'from' y 'to', o ninguno",
        )
    
    try:
        agg = OperationalAggregators(db)
        data = await agg.get_errors_detail(parsed_from, parsed_to)
        
        # Log with source info
        logger.info(
            f"[auth_operational_errors:{request_id}] completed "
            f"source_failures=login_attempts "
            f"source_rate_limits=login_attempts(reason=too_many_attempts) "
            f"source_lockouts=login_attempts(reason=account_locked) "
            f"source_http=not_instrumented "
            f"failures={data.login_failures_total} "
            f"rate_limits={data.rate_limit_triggers} "
            f"lockouts={data.lockouts_total} "
            f"http_4xx={data.http_4xx_count} http_5xx={data.http_5xx_count}"
        )
        
        return ErrorsDetailResponse(
            login_failures_by_reason=[
                LoginFailureByReasonItem(reason=f.reason, count=f.count)
                for f in data.login_failures_by_reason
            ],
            login_failures_total=data.login_failures_total,
            rate_limit_triggers=data.rate_limit_triggers,
            rate_limit_by_ip=data.rate_limit_by_ip,
            rate_limit_by_user=data.rate_limit_by_user,
            lockouts_total=data.lockouts_total,
            lockouts_by_ip=data.lockouts_by_ip,
            lockouts_by_user=data.lockouts_by_user,
            http_4xx_count=data.http_4xx_count,
            http_5xx_count=data.http_5xx_count,
            period_from=data.period_from,
            period_to=data.period_to,
            generated_at=data.generated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_operational_errors:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de errores",
        )


# Fin del archivo
