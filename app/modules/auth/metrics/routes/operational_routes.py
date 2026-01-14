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
import os
import time as _time
import uuid
from datetime import datetime

from sqlalchemy import text
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.metrics.schemas.operational_schemas import (
    OperationalSummaryResponse,
    SessionsDetailResponse,
    TopUserSessionsItem,
    ErrorsDetailResponse,
    LoginFailureByReasonItem,
    SecurityMetricsResponse,
    SecurityThresholds,
    SecurityAlert,
    MetricErrorResponse,
)
from app.modules.auth.metrics.schemas.operational_activation_schemas import (
    ActivationOperationalResponse,
    ActivationThresholds as ActivationThresholdsPydantic,
    ActivationAlert as ActivationAlertPydantic,
)
from app.modules.auth.metrics.schemas.operational_deliverability_schemas import (
    DeliverabilityOperationalResponse,
    DeliverabilityThresholds as DeliverabilityThresholdsPydantic,
    DeliverabilityAlert as DeliverabilityAlertPydantic,
)
from app.modules.auth.metrics.schemas.operational_password_reset_schemas import (
    PasswordResetOperationalResponse,
    PasswordResetThresholds as PasswordResetThresholdsPydantic,
    PasswordResetAlert as PasswordResetAlertPydantic,
)
from app.modules.auth.metrics.schemas.operational_errors_schemas import (
    ErrorsOperationalResponse,
    ErrorsThresholds as ErrorsThresholdsPydantic,
    ErrorsAlert as ErrorsAlertPydantic,
    LoginFailureByReasonItem as LoginFailureByReasonItemPydantic,
    ErrorsDailySeries as ErrorsDailySeriesPydantic,
)
from app.modules.auth.metrics.aggregators.operational_aggregators import (
    OperationalAggregators,
)
from app.modules.auth.metrics.aggregators.operational_security_aggregator import (
    SecurityAggregator,
)
from app.modules.auth.metrics.services.alert_state_service import AlertStateService
from app.modules.auth.metrics.schemas.operational_schemas import AlertStateInfo
from app.modules.auth.metrics.aggregators.operational_activation_aggregator import (
    ActivationOperationalAggregator,
)
from app.modules.auth.metrics.aggregators.operational_deliverability_aggregator import (
    DeliverabilityOperationalAggregator,
)
from app.modules.auth.metrics.aggregators.operational_password_reset_aggregator import (
    PasswordResetOperationalAggregator,
)
from app.modules.auth.metrics.aggregators.operational_errors_aggregator import (
    ErrorsOperationalAggregator,
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


@router.get("/errors", response_model=ErrorsOperationalResponse)
async def get_errors_detail(
    from_date: str = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Detalle de errores/fricción con alertas y umbrales.
    
    - Login failures by reason
    - Rate limits y lockouts
    - HTTP errors (not instrumented - siempre 0)
    - Alertas con severidad (HIGH/MEDIUM/LOW)
    - Thresholds como fuente de verdad
    
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
        agg = ErrorsOperationalAggregator(db)
        data = await agg.get_errors_operational_metrics(parsed_from, parsed_to)
        
        # Log with observability
        logger.info(
            f"[auth_operational_errors:{request_id}] completed "
            f"failures={data.login_failures_total} "
            f"rate_limits={data.rate_limit_triggers} "
            f"lockouts={data.lockouts_total} "
            f"alerts_high={data.alerts_high} "
            f"alerts_medium={data.alerts_medium} "
            f"alerts_low={data.alerts_low} "
            f"partial={data.errors_partial}"
        )
        
        if data.errors_partial:
            logger.info(f"[auth_operational_errors:{request_id}] partial=true http_instrumented=false")
        
        # Convert alerts
        alerts_pydantic = [
            ErrorsAlertPydantic(
                code=a.code,
                title=a.title,
                severity=a.severity.value,
                metric=a.metric,
                value=a.value,
                threshold=a.threshold,
                time_scope=a.time_scope,
                recommended_action=a.recommended_action,
                details=a.details,
            )
            for a in data.alerts
        ]
        
        # Convert failures by reason
        failures_by_reason = [
            LoginFailureByReasonItemPydantic(
                reason=f.reason,
                count=f.count,
                percentage=f.percentage,
            )
            for f in data.login_failures_by_reason
        ]
        
        # Convert daily series
        daily_series = [
            ErrorsDailySeriesPydantic(
                date=s.date,
                login_failures=s.login_failures,
                rate_limits=s.rate_limits,
                lockouts=s.lockouts,
            )
            for s in data.daily_series
        ]
        
        return ErrorsOperationalResponse(
            login_failures_total=data.login_failures_total,
            login_failures_by_reason=failures_by_reason,
            login_failure_rate=data.login_failure_rate,
            rate_limit_triggers=data.rate_limit_triggers,
            lockouts_total=data.lockouts_total,
            activation_failures=data.activation_failures,
            password_reset_failures=data.password_reset_failures,
            http_4xx_count=data.http_4xx_count,
            http_5xx_count=data.http_5xx_count,
            daily_series=daily_series,
            alerts=alerts_pydantic,
            alerts_high=data.alerts_high,
            alerts_medium=data.alerts_medium,
            alerts_low=data.alerts_low,
            thresholds=ErrorsThresholdsPydantic(**data.thresholds.to_dict()),
            from_date=data.from_date,
            to_date=data.to_date,
            generated_at=data.generated_at,
            notes=data.notes,
            errors_partial=data.errors_partial,
            http_instrumented=data.http_instrumented,
            activation_failures_instrumented=data.activation_failures_instrumented,
            password_reset_failures_instrumented=data.password_reset_failures_instrumented,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_operational_errors:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de errores",
        )


# ─────────────────────────────────────────────────────────────────
# Feature flag para diagnóstico (P0)
# Default OFF en producción para evitar ruido/filtración
# ─────────────────────────────────────────────────────────────────
AUTH_SECURITY_DIAGNOSTICS_ENABLED = os.getenv(
    "AUTH_SECURITY_DIAGNOSTICS_ENABLED", "0"
).lower() in ("1", "true", "yes")


@router.get("/security", response_model=SecurityMetricsResponse)
async def get_security_metrics(
    from_date: str = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Métricas de seguridad operativa.
    
    NOTA: Las funciones fn_metrics_sessions_* son SECURITY DEFINER con OWNER=postgres,
    lo que bypasea RLS automáticamente. NO se requiere service_role en la conexión.
    
    Diagnóstico opcional (AUTH_SECURITY_DIAGNOSTICS_ENABLED=1):
    - Verifica current_user y role de conexión
    - Ejecuta smoke test de fn_metrics_sessions_all
    - Refleja errores en data.errors y data.notes
    
    Query params:
    - from: Fecha inicio (YYYY-MM-DD) - opcional (default: -7 días)
    - to: Fecha fin (YYYY-MM-DD) - opcional (default: hoy)
    """
    request_id = str(uuid.uuid4())[:8]
    server_time_utc = datetime.utcnow().isoformat() + "Z"
    
    # Acumuladores para diagnóstico (se agregan al response si fallan)
    diag_errors: list = []
    diag_notes: list = []
    
    # ─────────────────────────────────────────────────────────────────
    # A) DIAGNÓSTICO DE CONEXIÓN (solo si flag ON)
    # ─────────────────────────────────────────────────────────────────
    if AUTH_SECURITY_DIAGNOSTICS_ENABLED:
        try:
            # 1. Obtener identidad de conexión (compacto)
            diag_result = await db.execute(text("""
                SELECT current_user, current_setting('role', true)
            """))
            diag_row = diag_result.first()
            conn_user = diag_row[0] if diag_row else "unknown"
            conn_role = diag_row[1] if diag_row else "unknown"
            
            # 2. Smoke test de la función
            smoke_start = _time.perf_counter()
            smoke_result = await db.execute(text("""
                SELECT sessions_active
                FROM public.fn_metrics_sessions_all(1)
            """))
            smoke_row = smoke_result.first()
            smoke_ms = (_time.perf_counter() - smoke_start) * 1000
            
            sessions_active_val = smoke_row[0] if smoke_row else None
            smoke_ok = sessions_active_val is not None
            
            # Log compacto y seguro
            logger.info(
                f"[auth_security:{request_id}] diag "
                f"user={conn_user} role={conn_role} "
                f"smoke_ok={smoke_ok} sessions_active={sessions_active_val} "
                f"smoke_ms={smoke_ms:.1f}"
            )
            
        except Exception as e:
            error_type = type(e).__name__
            # Mensaje seguro (sin detalles sensibles)
            safe_message = str(e)[:200] if str(e) else "Unknown error"
            
            diag_errors.append({
                "name": "sessions_smoke_test",
                "error_type": error_type,
                "message": safe_message,
            })
            diag_notes.append("diag:sessions_smoke_test_failed")
            
            logger.warning(
                f"[auth_security:{request_id}] smoke_test FAILED "
                f"error_type={error_type}"
            )
    
    logger.info(
        f"[auth_security:{request_id}] from={from_date} to={to_date} "
        f"server_time={server_time_utc} diag_enabled={AUTH_SECURITY_DIAGNOSTICS_ENABLED}"
    )
    
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
        agg = SecurityAggregator(db)
        data = await agg.get_security_metrics(parsed_from, parsed_to)
        
        # Agregar errores del diagnóstico al response
        if diag_errors:
            from app.modules.auth.metrics.aggregators.operational_security_aggregator import MetricError
            for err in diag_errors:
                data.errors.append(MetricError(
                    name=err["name"],
                    error_type=err["error_type"],
                    message=err["message"],
                ))
            data.partial = True
        
        # Agregar notas del diagnóstico
        for note in diag_notes:
            if note not in data.notes:
                data.notes.append(note)
        # ─────────────────────────────────────────────────────────────────
        # OVERLAY: Aplicar estados de alertas (ack/snooze)
        # ─────────────────────────────────────────────────────────────────
        alert_keys = [a.code for a in data.alerts]
        overlays = {}
        
        if alert_keys:
            try:
                from datetime import datetime as dt_mod
                scope_from_date = dt_mod.strptime(data.from_date, "%Y-%m-%d").date() if data.from_date else None
                scope_to_date = dt_mod.strptime(data.to_date, "%Y-%m-%d").date() if data.to_date else None
                
                alert_state_service = AlertStateService(db)
                overlays = await alert_state_service.get_overlays_for_alerts(
                    alert_keys=alert_keys,
                    scope_from=scope_from_date,
                    scope_to=scope_to_date,
                )
            except Exception as overlay_err:
                logger.warning(
                    f"[auth_security:{request_id}] overlay fetch failed: {overlay_err}"
                )
                # Continue without overlay
        
        logger.info(
            f"[auth_security:{request_id}] completed "
            f"attempts={data.login_attempts_total} "
            f"failed={data.login_attempts_failed} "
            f"sessions={data.sessions_active} "
            f"partial={data.partial} "
            f"errors_count={len(data.errors)}"
        )
        
        # Convert alerts from dataclass to pydantic model with overlay
        alerts_pydantic = []
        alerts_high_actionable = 0
        alerts_medium_actionable = 0
        alerts_low_actionable = 0
        
        for a in data.alerts:
            overlay = overlays.get(a.code)
            
            # Determinar si es "actionable" (no snoozed/ack)
            is_actionable = True
            state_info = None
            
            if overlay:
                is_actionable = not (overlay.is_snoozed or overlay.is_acknowledged)
                state_info = AlertStateInfo(
                    status=overlay.status.value,
                    is_snoozed=overlay.is_snoozed,
                    is_acknowledged=overlay.is_acknowledged,
                    snoozed_until=overlay.snoozed_until.isoformat() if overlay.snoozed_until else None,
                    acknowledged_at=overlay.acknowledged_at.isoformat() if overlay.acknowledged_at else None,
                    acknowledged_by=str(overlay.acknowledged_by) if overlay.acknowledged_by else None,
                    comment=overlay.comment,
                )
            
            # Contar solo alertas actionable
            if is_actionable:
                if a.severity.value == "high":
                    alerts_high_actionable += 1
                elif a.severity.value == "medium":
                    alerts_medium_actionable += 1
                else:
                    alerts_low_actionable += 1
            
            alerts_pydantic.append(SecurityAlert(
                code=a.code,
                title=a.title,
                severity=a.severity.value,
                metric=a.metric,
                value=a.value,
                threshold=a.threshold,
                time_scope=a.time_scope,
                recommended_action=a.recommended_action,
                details=a.details,
                state=state_info,
            ))
        
        # Convert errors from dataclass to pydantic model
        errors_pydantic = [
            MetricErrorResponse(
                name=e.name,
                error_type=e.error_type,
                message=e.message,
            )
            for e in data.errors
        ]
        
        return SecurityMetricsResponse(
            login_attempts_total=data.login_attempts_total,
            login_attempts_failed=data.login_attempts_failed,
            login_attempts_success=data.login_attempts_success,
            login_failure_rate=data.login_failure_rate,
            ips_with_high_failures=data.ips_with_high_failures,
            users_with_high_failures=data.users_with_high_failures,
            lockouts_triggered=data.lockouts_triggered,
            accounts_locked_active=data.accounts_locked_active,
            sessions_active=data.sessions_active,
            users_with_multiple_sessions=data.users_with_multiple_sessions,
            sessions_last_24h=data.sessions_last_24h,
            sessions_expiring_24h=data.sessions_expiring_24h,
            password_reset_requests=data.password_reset_requests,
            password_reset_completed=data.password_reset_completed,
            password_reset_abandoned=data.password_reset_abandoned,
            reset_requests_by_user_gt_1=data.reset_requests_by_user_gt_1,
            users_with_failed_login_and_reset=data.users_with_failed_login_and_reset,
            accounts_with_login_but_no_recent_session=data.accounts_with_login_but_no_recent_session,
            alerts=alerts_pydantic,
            alerts_high=alerts_high_actionable,
            alerts_medium=alerts_medium_actionable,
            alerts_low=alerts_low_actionable,
            alerts_actionable=alerts_high_actionable + alerts_medium_actionable + alerts_low_actionable,
            from_date=data.from_date,
            to_date=data.to_date,
            generated_at=data.generated_at,
            notes=data.notes,
            thresholds=SecurityThresholds(**data.thresholds.to_dict()),
            errors=errors_pydantic,
            partial=data.partial,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_security:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de seguridad",
        )


@router.get("/activation", response_model=ActivationOperationalResponse)
async def get_activation_operational_metrics(
    from_date: str = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Métricas operativas de activación de cuentas.
    
    - Emails enviados: correos de activación en el periodo
    - Activaciones: completadas, expiradas, pendientes
    - Tiempos: tiempo promedio de activación
    - Alertas: problemas detectados con severidad
    
    Query params:
    - from: Fecha inicio (YYYY-MM-DD) - opcional (default: -7 días)
    - to: Fecha fin (YYYY-MM-DD) - opcional (default: hoy)
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_operational_activation:{request_id}] from={from_date} to={to_date}")
    
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
        agg = ActivationOperationalAggregator(db)
        data = await agg.get_activation_operational_metrics(parsed_from, parsed_to)
        
        logger.info(
            f"[auth_operational_activation:{request_id}] completed "
            f"emails_sent={data.activation_emails_sent} "
            f"completed={data.activations_completed} "
            f"expired={data.activation_tokens_expired} "
            f"alerts_high={data.alerts_high} "
            f"alerts_medium={data.alerts_medium}"
        )
        
        # Convert alerts from dataclass to pydantic model
        alerts_pydantic = [
            ActivationAlertPydantic(
                code=a.code,
                title=a.title,
                severity=a.severity.value,  # Enum -> string
                metric=a.metric,
                value=a.value,
                threshold=a.threshold,
                time_scope=a.time_scope,
                recommended_action=a.recommended_action,
                details=a.details,
            )
            for a in data.alerts
        ]
        
        return ActivationOperationalResponse(
            activation_emails_sent=data.activation_emails_sent,
            activations_completed=data.activations_completed,
            activation_tokens_expired=data.activation_tokens_expired,
            activation_resends=data.activation_resends,
            avg_time_to_activate_seconds=data.avg_time_to_activate_seconds,
            pending_tokens_stock_24h=data.pending_tokens_stock_24h,
            pending_created_in_period_24h=data.pending_created_in_period_24h,
            users_with_multiple_resends=data.users_with_multiple_resends,
            activation_tokens_active=data.activation_tokens_active,
            activation_tokens_expired_stock=data.activation_tokens_expired_stock,
            activation_failure_rate=data.activation_failure_rate,
            alerts=alerts_pydantic,
            alerts_high=data.alerts_high,
            alerts_medium=data.alerts_medium,
            alerts_low=data.alerts_low,
            from_date=data.from_date,
            to_date=data.to_date,
            generated_at=data.generated_at,
            notes=data.notes,
            thresholds=ActivationThresholdsPydantic(**data.thresholds.to_dict()),
            email_events_source=data.email_events_source,
            email_events_partial=data.email_events_partial,
            resends_instrumented=data.resends_instrumented,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_operational_activation:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de activación",
        )


@router.get("/deliverability", response_model=DeliverabilityOperationalResponse)
async def get_deliverability_operational_metrics(
    from_date: str = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Métricas operativas de entregabilidad de correos.
    
    - Envíos: correos enviados, entregados, rebotados, fallidos
    - Tasas: entrega, rebote, quejas spam
    - Calidad: usuarios con múltiples rebotes
    - Alertas: problemas detectados con severidad
    
    Query params:
    - from: Fecha inicio (YYYY-MM-DD) - opcional (default: -7 días)
    - to: Fecha fin (YYYY-MM-DD) - opcional (default: hoy)
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_operational_deliverability:{request_id}] from={from_date} to={to_date}")
    
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
        agg = DeliverabilityOperationalAggregator(db)
        data = await agg.get_deliverability_operational_metrics(parsed_from, parsed_to)
        
        logger.info(
            f"[auth_operational_deliverability:{request_id}] completed "
            f"sent={data.emails_sent} "
            f"delivered={data.emails_delivered} "
            f"bounced={data.emails_bounced} "
            f"complained={data.emails_complained} "
            f"alerts_high={data.alerts_high} "
            f"alerts_medium={data.alerts_medium}"
        )
        
        # Convert alerts from dataclass to pydantic model
        alerts_pydantic = [
            DeliverabilityAlertPydantic(
                code=a.code,
                title=a.title,
                severity=a.severity.value,  # Enum -> string
                metric=a.metric,
                value=a.value,
                threshold=a.threshold,
                time_scope=a.time_scope,
                recommended_action=a.recommended_action,
                details=a.details,
            )
            for a in data.alerts
        ]
        
        return DeliverabilityOperationalResponse(
            emails_sent=data.emails_sent,
            emails_delivered=data.emails_delivered,
            emails_bounced=data.emails_bounced,
            emails_failed=data.emails_failed,
            emails_complained=data.emails_complained,
            delivery_rate=data.delivery_rate,
            bounce_rate=data.bounce_rate,
            complaint_rate=data.complaint_rate,
            users_with_multiple_bounces=data.users_with_multiple_bounces,
            alerts=alerts_pydantic,
            alerts_high=data.alerts_high,
            alerts_medium=data.alerts_medium,
            alerts_low=data.alerts_low,
            from_date=data.from_date,
            to_date=data.to_date,
            generated_at=data.generated_at,
            notes=data.notes,
            thresholds=DeliverabilityThresholdsPydantic(**data.thresholds.to_dict()),
            email_events_source=data.email_events_source,
            email_events_partial=data.email_events_partial,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_operational_deliverability:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de entregabilidad",
        )


@router.get("/password-reset", response_model=PasswordResetOperationalResponse)
async def get_password_reset_operational_metrics(
    from_date: str = Query(None, alias="from", description="Fecha inicio (YYYY-MM-DD)"),
    to_date: str = Query(None, alias="to", description="Fecha fin (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Métricas operativas de recuperación de contraseña.
    
    - Solicitudes: resets solicitados, enviados, completados
    - Tiempos: tiempo promedio de reset
    - Pendientes: tokens sin usar
    - Alertas: problemas detectados con severidad
    
    Query params:
    - from: Fecha inicio (YYYY-MM-DD) - opcional (default: -7 días)
    - to: Fecha fin (YYYY-MM-DD) - opcional (default: hoy)
    """
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[auth_operational_password_reset:{request_id}] from={from_date} to={to_date}")
    
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
        agg = PasswordResetOperationalAggregator(db)
        data = await agg.get_password_reset_operational_metrics(parsed_from, parsed_to)
        
        logger.info(
            f"[auth_operational_password_reset:{request_id}] completed "
            f"requests={data.password_reset_requests} "
            f"emails_sent={data.password_reset_emails_sent} "
            f"completed={data.password_reset_completed} "
            f"expired={data.password_reset_expired} "
            f"alerts_high={data.alerts_high} "
            f"alerts_medium={data.alerts_medium}"
        )
        
        # Convert alerts from dataclass to pydantic model
        alerts_pydantic = [
            PasswordResetAlertPydantic(
                code=a.code,
                title=a.title,
                severity=a.severity.value,  # Enum -> string
                metric=a.metric,
                value=a.value,
                threshold=a.threshold,
                time_scope=a.time_scope,
                recommended_action=a.recommended_action,
                details=a.details,
            )
            for a in data.alerts
        ]
        
        return PasswordResetOperationalResponse(
            password_reset_requests=data.password_reset_requests,
            password_reset_emails_sent=data.password_reset_emails_sent,
            password_reset_completed=data.password_reset_completed,
            password_reset_expired=data.password_reset_expired,
            avg_time_to_reset_seconds=data.avg_time_to_reset_seconds,
            pending_tokens_stock_24h=data.pending_tokens_stock_24h,
            pending_created_in_period_24h=data.pending_created_in_period_24h,
            users_with_multiple_requests=data.users_with_multiple_requests,
            password_reset_tokens_active=data.password_reset_tokens_active,
            password_reset_tokens_expired_stock=data.password_reset_tokens_expired_stock,
            password_reset_failure_rate=data.password_reset_failure_rate,
            alerts=alerts_pydantic,
            alerts_high=data.alerts_high,
            alerts_medium=data.alerts_medium,
            alerts_low=data.alerts_low,
            from_date=data.from_date,
            to_date=data.to_date,
            generated_at=data.generated_at,
            notes=data.notes,
            thresholds=PasswordResetThresholdsPydantic(**data.thresholds.to_dict()),
            email_events_source=data.email_events_source,
            email_events_partial=data.email_events_partial,
            resends_instrumented=data.resends_instrumented,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[auth_operational_password_reset:{request_id}] fatal: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error interno al calcular métricas de password reset",
        )


# Fin del archivo
