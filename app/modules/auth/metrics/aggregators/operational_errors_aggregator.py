# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/operational_errors_aggregator.py

Agregador para métricas operativas de errores de Auth.

Fuentes de datos:
- public.login_attempts: intentos fallidos, razones, rate limits, lockouts
- public.auth_email_events: fallos de email (activación, password reset)
- HTTP errors: NO instrumentados (devuelve 0 + nota)

Autor: Sistema
Fecha: 2026-01-06
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import List, Optional, Union, Dict, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Import enum from central location
from app.modules.auth.enums.login_failure_reason_enum import LoginFailureReason

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Umbrales configurables (fuente de verdad)
# ─────────────────────────────────────────────────────────────────

LOGIN_FAILURES_WARN = 10
LOGIN_FAILURES_HIGH = 50

LOGIN_FAILURE_RATE_WARN = 0.15  # 15%
LOGIN_FAILURE_RATE_HIGH = 0.35  # 35%

RATE_LIMITS_WARN = 3
RATE_LIMITS_HIGH = 15

LOCKOUTS_WARN = 2
LOCKOUTS_HIGH = 10

HTTP_5XX_WARN = 5
HTTP_5XX_HIGH = 20

HTTP_4XX_WARN = 20
HTTP_4XX_HIGH = 100

FAILED_REASONS_CONCENTRATION_WARN = 0.50  # 50%
FAILED_REASONS_CONCENTRATION_HIGH = 0.80  # 80%


class AlertSeverity(str, Enum):
    """Niveles de severidad."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ErrorsAlert:
    """Estructura de una alerta de errores."""
    code: str
    title: str
    severity: AlertSeverity
    metric: str
    value: Union[int, float]
    threshold: str
    time_scope: str
    recommended_action: str
    details: Optional[str] = None


@dataclass
class ErrorsThresholds:
    """Umbrales (fuente de verdad para frontend)."""
    login_failures_warn: int = LOGIN_FAILURES_WARN
    login_failures_high: int = LOGIN_FAILURES_HIGH
    login_failure_rate_warn: float = LOGIN_FAILURE_RATE_WARN
    login_failure_rate_high: float = LOGIN_FAILURE_RATE_HIGH
    rate_limits_warn: int = RATE_LIMITS_WARN
    rate_limits_high: int = RATE_LIMITS_HIGH
    lockouts_warn: int = LOCKOUTS_WARN
    lockouts_high: int = LOCKOUTS_HIGH
    http_5xx_warn: int = HTTP_5XX_WARN
    http_5xx_high: int = HTTP_5XX_HIGH
    http_4xx_warn: int = HTTP_4XX_WARN
    http_4xx_high: int = HTTP_4XX_HIGH
    failed_reasons_concentration_warn: float = FAILED_REASONS_CONCENTRATION_WARN
    failed_reasons_concentration_high: float = FAILED_REASONS_CONCENTRATION_HIGH

    def to_dict(self) -> dict:
        return {
            "login_failures_warn": self.login_failures_warn,
            "login_failures_high": self.login_failures_high,
            "login_failure_rate_warn": self.login_failure_rate_warn,
            "login_failure_rate_high": self.login_failure_rate_high,
            "rate_limits_warn": self.rate_limits_warn,
            "rate_limits_high": self.rate_limits_high,
            "lockouts_warn": self.lockouts_warn,
            "lockouts_high": self.lockouts_high,
            "http_5xx_warn": self.http_5xx_warn,
            "http_5xx_high": self.http_5xx_high,
            "http_4xx_warn": self.http_4xx_warn,
            "http_4xx_high": self.http_4xx_high,
            "failed_reasons_concentration_warn": self.failed_reasons_concentration_warn,
            "failed_reasons_concentration_high": self.failed_reasons_concentration_high,
        }


@dataclass
class LoginFailureByReason:
    """Fallo por razón."""
    reason: str
    count: int
    percentage: Optional[float] = None


@dataclass
class DailySeries:
    """Serie diaria."""
    date: str
    login_failures: int = 0
    rate_limits: int = 0
    lockouts: int = 0


@dataclass
class ErrorsOperationalData:
    """Métricas operativas de errores."""
    
    # Periodo
    login_failures_total: int = 0
    login_failures_by_reason: List[LoginFailureByReason] = field(default_factory=list)
    login_failure_rate: Optional[float] = None
    
    rate_limit_triggers: int = 0
    lockouts_total: int = 0
    
    activation_failures: int = 0
    password_reset_failures: int = 0
    
    http_4xx_count: int = 0
    http_5xx_count: int = 0
    
    # Series
    daily_series: List[DailySeries] = field(default_factory=list)
    
    # Alertas
    alerts: List[ErrorsAlert] = field(default_factory=list)
    alerts_high: int = 0
    alerts_medium: int = 0
    alerts_low: int = 0
    
    # Metadata
    from_date: str = ""
    to_date: str = ""
    generated_at: str = ""
    notes: List[str] = field(default_factory=list)
    
    thresholds: ErrorsThresholds = field(default_factory=ErrorsThresholds)
    
    # Parcialidad
    errors_partial: bool = False
    has_partial_sections: bool = False
    partial_sections: List[str] = field(default_factory=list)
    http_instrumented: bool = False
    activation_failures_instrumented: bool = False
    password_reset_failures_instrumented: bool = False


class ErrorsOperationalAggregator:
    """Agregador para métricas operativas de errores."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _build_range(self, from_date: date, to_date: date):
        """Construye rango half-open UTC."""
        from_ts = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        return from_ts, to_ts
    
    async def get_errors_operational_metrics(
        self,
        from_date: Optional[Union[str, date]] = None,
        to_date: Optional[Union[str, date]] = None,
    ) -> ErrorsOperationalData:
        """Obtiene métricas operativas de errores."""
        
        # Default: últimos 7 días
        if not from_date or not to_date:
            today = datetime.now(timezone.utc).date()
            from_d = today - timedelta(days=7)
            to_d = today
        else:
            # Soportar str o date (patrón canónico temporal)
            from_d = (
                datetime.strptime(from_date, "%Y-%m-%d").date()
                if isinstance(from_date, str)
                else from_date
            )
            to_d = (
                datetime.strptime(to_date, "%Y-%m-%d").date()
                if isinstance(to_date, str)
                else to_date
            )
        
        from_ts, to_ts = self._build_range(from_d, to_d)
        
        logger.info(
            "get_errors_operational_metrics from=%s to=%s from_ts=%s to_ts=%s",
            from_d, to_d, from_ts, to_ts
        )
        
        notes: List[str] = []
        
        # ─────────────────────────────────────────────────────────────────
        # 1. LOGIN FAILURES (total y por razón)
        # ─────────────────────────────────────────────────────────────────
        login_failures_total = 0
        login_attempts_total = 0
        login_failures_by_reason: List[LoginFailureByReason] = []
        
        try:
            # Total intentos y fallos
            q = text("""
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE NOT success)::int AS failed
                FROM public.login_attempts
                WHERE created_at >= :from_ts
                  AND created_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row:
                login_attempts_total = int(row.total or 0)
                login_failures_total = int(row.failed or 0)
        except Exception as e:
            logger.debug("login_failures_total query failed: %s", e)
        
        # Fallos por razón (top 10)
        try:
            q = text("""
                SELECT reason, COUNT(*)::int AS cnt
                FROM public.login_attempts
                WHERE NOT success
                  AND created_at >= :from_ts
                  AND created_at < :to_ts
                GROUP BY reason
                ORDER BY cnt DESC
                LIMIT 10
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            rows = res.fetchall()
            for r in rows:
                reason = r.reason or "unknown"
                cnt = int(r.cnt or 0)
                pct = round(cnt / login_failures_total, 4) if login_failures_total > 0 else None
                login_failures_by_reason.append(
                    LoginFailureByReason(reason=reason, count=cnt, percentage=pct)
                )
        except Exception as e:
            logger.debug("login_failures_by_reason query failed: %s", e)
        
        # Tasa de fallo
        login_failure_rate: Optional[float] = None
        if login_attempts_total > 0:
            login_failure_rate = round(login_failures_total / login_attempts_total, 4)
        
        # ─────────────────────────────────────────────────────────────────
        # 2. RATE LIMITS Y LOCKOUTS
        # ─────────────────────────────────────────────────────────────────
        rate_limit_triggers = 0
        lockouts_total = 0
        
        try:
            q = text("""
                SELECT
                    COUNT(*) FILTER (WHERE reason = :reason_rate_limit)::int AS rate_limits,
                    COUNT(*) FILTER (WHERE reason = :reason_lockout)::int AS lockouts
                FROM public.login_attempts
                WHERE NOT success
                  AND created_at >= :from_ts
                  AND created_at < :to_ts
            """)
            res = await self.db.execute(q, {
                "from_ts": from_ts,
                "to_ts": to_ts,
                "reason_rate_limit": LoginFailureReason.rate_limited.value,
                "reason_lockout": LoginFailureReason.blocked_user.value,
            })
            row = res.first()
            if row:
                rate_limit_triggers = int(row.rate_limits or 0)
                lockouts_total = int(row.lockouts or 0)
        except Exception as e:
            logger.debug("rate_limits/lockouts query failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────────
        # 3. ACTIVATION Y PASSWORD RESET FAILURES (no instrumentado)
        # ─────────────────────────────────────────────────────────────────
        activation_failures = 0
        password_reset_failures = 0
        activation_failures_instrumented = False
        password_reset_failures_instrumented = False
        
        # Por ahora no hay señales específicas - marcar como no instrumentado
        notes.append("Fallos de activación y password reset: no instrumentado aún.")
        
        # ─────────────────────────────────────────────────────────────────
        # 4. HTTP ERRORS (from http_request_metrics_daily if available)
        # ─────────────────────────────────────────────────────────────────
        http_4xx_count = 0
        http_5xx_count = 0
        http_instrumented = False
        
        try:
            # Robust query: returns n_days (number of days with data), total_4xx, total_5xx
            # http_instrumented = True if n_days > 0 (table exists and has data)
            q = text("""
                SELECT 
                    COUNT(*)::int AS n_days,
                    COALESCE(SUM(http_4xx_count), 0)::int AS total_4xx,
                    COALESCE(SUM(http_5xx_count), 0)::int AS total_5xx
                FROM public.http_request_metrics_daily
                WHERE date >= :from_date
                  AND date <= :to_date
                  AND scope = 'auth'
            """)
            res = await self.db.execute(q, {"from_date": from_d, "to_date": to_d})
            row = res.first()
            
            n_days = int(row.n_days) if row else 0
            http_instrumented = n_days > 0
            
            if http_instrumented:
                http_4xx_count = int(row.total_4xx or 0)
                http_5xx_count = int(row.total_5xx or 0)
                logger.debug("http_metrics from db: n_days=%d 4xx=%d 5xx=%d", n_days, http_4xx_count, http_5xx_count)
            else:
                # Table exists but no data for period/scope
                notes.append("Errores HTTP (4xx/5xx): sin datos en el periodo.")
        except Exception as e:
            # Table doesn't exist or query failed - not instrumented
            logger.debug("http_metrics query failed (table may not exist): %s", e)
            notes.append("Errores HTTP (4xx/5xx): no instrumentado.")
        
        # ─────────────────────────────────────────────────────────────────
        # 5. SERIE DIARIA (con relleno de días faltantes)
        # ─────────────────────────────────────────────────────────────────
        daily_series: List[DailySeries] = []
        daily_data_map: Dict[str, DailySeries] = {}
        
        try:
            q = text("""
                SELECT 
                    DATE(created_at) AS day,
                    COUNT(*) FILTER (WHERE NOT success)::int AS failures,
                    COUNT(*) FILTER (WHERE reason = :reason_rate_limit)::int AS rate_limits,
                    COUNT(*) FILTER (WHERE reason = :reason_lockout)::int AS lockouts
                FROM public.login_attempts
                WHERE created_at >= :from_ts
                  AND created_at < :to_ts
                GROUP BY DATE(created_at)
                ORDER BY day
            """)
            res = await self.db.execute(q, {
                "from_ts": from_ts,
                "to_ts": to_ts,
                "reason_rate_limit": LoginFailureReason.rate_limited.value,
                "reason_lockout": LoginFailureReason.blocked_user.value,
            })
            rows = res.fetchall()
            for r in rows:
                day_str = r.day.isoformat() if r.day else ""
                if day_str:
                    daily_data_map[day_str] = DailySeries(
                        date=day_str,
                        login_failures=int(r.failures or 0),
                        rate_limits=int(r.rate_limits or 0),
                        lockouts=int(r.lockouts or 0),
                    )
        except Exception as e:
            logger.debug("daily_series query failed: %s", e)
        
        # Rellenar días faltantes con 0 para gráfico continuo
        current_day = from_d
        while current_day <= to_d:
            day_str = current_day.isoformat()
            if day_str in daily_data_map:
                daily_series.append(daily_data_map[day_str])
            else:
                daily_series.append(DailySeries(
                    date=day_str,
                    login_failures=0,
                    rate_limits=0,
                    lockouts=0,
                ))
            current_day += timedelta(days=1)
        
        # ─────────────────────────────────────────────────────────────────
        # 6. GENERAR ALERTAS
        # ─────────────────────────────────────────────────────────────────
        alerts = self._generate_alerts(
            login_failures_total=login_failures_total,
            login_failure_rate=login_failure_rate,
            rate_limit_triggers=rate_limit_triggers,
            lockouts_total=lockouts_total,
            http_5xx_count=http_5xx_count,
            login_failures_by_reason=login_failures_by_reason,
        )
        
        # Aplicar regla de supresión LOW
        alerts = self._apply_severity_suppression(alerts)
        
        alerts_high = sum(1 for a in alerts if a.severity == AlertSeverity.HIGH)
        alerts_medium = sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM)
        alerts_low = sum(1 for a in alerts if a.severity == AlertSeverity.LOW)
        
        # Log observabilidad
        alert_codes = [a.code for a in alerts]
        max_severity = (
            "HIGH" if alerts_high > 0 else
            "MEDIUM" if alerts_medium > 0 else
            "LOW" if alerts_low > 0 else
            "NONE"
        )
        
        logger.info(
            "errors_metrics_observability "
            f"login_failures={login_failures_total} "
            f"rate_limits={rate_limit_triggers} "
            f"lockouts={lockouts_total} "
            f"alerts_codes={alert_codes} "
            f"max_severity={max_severity}"
        )
        
        # Marcar parcial si hay señales secundarias faltantes
        # Las métricas principales (login_failures, rate_limits, lockouts) siempre están disponibles
        partial_sections: List[str] = []
        if not http_instrumented:
            partial_sections.append("http")
        if not activation_failures_instrumented:
            partial_sections.append("activation_failures")
        if not password_reset_failures_instrumented:
            partial_sections.append("password_reset_failures")
        
        errors_partial = len(partial_sections) > 0
        has_partial_sections = errors_partial
        
        if errors_partial:
            logger.info(f"auth_operational_errors_partial reasons={partial_sections}")
        
        return ErrorsOperationalData(
            login_failures_total=login_failures_total,
            login_failures_by_reason=login_failures_by_reason,
            login_failure_rate=login_failure_rate,
            rate_limit_triggers=rate_limit_triggers,
            lockouts_total=lockouts_total,
            activation_failures=activation_failures,
            password_reset_failures=password_reset_failures,
            http_4xx_count=http_4xx_count,
            http_5xx_count=http_5xx_count,
            daily_series=daily_series,
            alerts=alerts,
            alerts_high=alerts_high,
            alerts_medium=alerts_medium,
            alerts_low=alerts_low,
            from_date=from_d.isoformat(),
            to_date=to_d.isoformat(),
            generated_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
            thresholds=ErrorsThresholds(),
            errors_partial=errors_partial,
            has_partial_sections=has_partial_sections,
            partial_sections=partial_sections,
            http_instrumented=http_instrumented,
            activation_failures_instrumented=activation_failures_instrumented,
            password_reset_failures_instrumented=password_reset_failures_instrumented,
        )
    
    def _generate_alerts(
        self,
        login_failures_total: int,
        login_failure_rate: Optional[float],
        rate_limit_triggers: int,
        lockouts_total: int,
        http_5xx_count: int,
        login_failures_by_reason: List[LoginFailureByReason],
    ) -> List[ErrorsAlert]:
        """Genera alertas basadas en umbrales."""
        alerts: List[ErrorsAlert] = []
        
        # ─── Login Failures ───
        if login_failures_total >= LOGIN_FAILURES_HIGH:
            alerts.append(ErrorsAlert(
                code="HIGH_LOGIN_FAILURES",
                title="Muchos fallos de login",
                severity=AlertSeverity.HIGH,
                metric="login_failures_total",
                value=login_failures_total,
                threshold=f">= {LOGIN_FAILURES_HIGH} fallos",
                time_scope="periodo",
                recommended_action="Revisar si hay ataque de fuerza bruta o problemas de UX en el login.",
            ))
        elif login_failures_total >= LOGIN_FAILURES_WARN:
            alerts.append(ErrorsAlert(
                code="WARN_LOGIN_FAILURES",
                title="Fallos de login elevados",
                severity=AlertSeverity.MEDIUM,
                metric="login_failures_total",
                value=login_failures_total,
                threshold=f">= {LOGIN_FAILURES_WARN} fallos",
                time_scope="periodo",
                recommended_action="Monitorear tendencia de fallos de login.",
            ))
        elif login_failures_total > 0:
            alerts.append(ErrorsAlert(
                code="LOW_LOGIN_FAILURES",
                title="Fallos de login detectados",
                severity=AlertSeverity.LOW,
                metric="login_failures_total",
                value=login_failures_total,
                threshold="> 0 fallos",
                time_scope="periodo",
                recommended_action="Revisar razones de fallo más comunes.",
            ))
        
        # ─── Login Failure Rate ───
        if login_failure_rate is not None:
            if login_failure_rate >= LOGIN_FAILURE_RATE_HIGH:
                alerts.append(ErrorsAlert(
                    code="HIGH_LOGIN_FAILURE_RATE",
                    title="Tasa de fallo de login crítica",
                    severity=AlertSeverity.HIGH,
                    metric="login_failure_rate",
                    value=login_failure_rate,
                    threshold=f">= {int(LOGIN_FAILURE_RATE_HIGH * 100)}%",
                    time_scope="periodo",
                    recommended_action="Investigar causa de alta tasa de rechazo. Posible ataque o problema sistémico.",
                ))
            elif login_failure_rate >= LOGIN_FAILURE_RATE_WARN:
                alerts.append(ErrorsAlert(
                    code="WARN_LOGIN_FAILURE_RATE",
                    title="Tasa de fallo de login elevada",
                    severity=AlertSeverity.MEDIUM,
                    metric="login_failure_rate",
                    value=login_failure_rate,
                    threshold=f">= {int(LOGIN_FAILURE_RATE_WARN * 100)}%",
                    time_scope="periodo",
                    recommended_action="Revisar UX del formulario de login o posibles intentos de acceso no autorizados.",
                ))
        
        # ─── Rate Limits ───
        if rate_limit_triggers >= RATE_LIMITS_HIGH:
            alerts.append(ErrorsAlert(
                code="HIGH_RATE_LIMITS",
                title="Muchos rate limits activados",
                severity=AlertSeverity.HIGH,
                metric="rate_limit_triggers",
                value=rate_limit_triggers,
                threshold=f">= {RATE_LIMITS_HIGH} eventos",
                time_scope="periodo",
                recommended_action="Posible ataque de fuerza bruta. Revisar IPs bloqueadas y considerar medidas adicionales.",
            ))
        elif rate_limit_triggers >= RATE_LIMITS_WARN:
            alerts.append(ErrorsAlert(
                code="WARN_RATE_LIMITS",
                title="Rate limits activados",
                severity=AlertSeverity.MEDIUM,
                metric="rate_limit_triggers",
                value=rate_limit_triggers,
                threshold=f">= {RATE_LIMITS_WARN} eventos",
                time_scope="periodo",
                recommended_action="Monitorear origen de intentos excesivos.",
            ))
        
        # ─── Lockouts ───
        if lockouts_total >= LOCKOUTS_HIGH:
            alerts.append(ErrorsAlert(
                code="HIGH_LOCKOUTS",
                title="Muchas cuentas bloqueadas",
                severity=AlertSeverity.HIGH,
                metric="lockouts_total",
                value=lockouts_total,
                threshold=f">= {LOCKOUTS_HIGH} bloqueos",
                time_scope="periodo",
                recommended_action="Revisar si los bloqueos son legítimos o si hay problemas de usabilidad.",
            ))
        elif lockouts_total >= LOCKOUTS_WARN:
            alerts.append(ErrorsAlert(
                code="WARN_LOCKOUTS",
                title="Cuentas bloqueadas",
                severity=AlertSeverity.MEDIUM,
                metric="lockouts_total",
                value=lockouts_total,
                threshold=f">= {LOCKOUTS_WARN} bloqueos",
                time_scope="periodo",
                recommended_action="Verificar que los usuarios puedan desbloquear sus cuentas fácilmente.",
            ))
        
        # ─── Concentración de razones ───
        if login_failures_by_reason and login_failures_total > 0:
            top_reason = login_failures_by_reason[0] if login_failures_by_reason else None
            if top_reason and top_reason.percentage:
                if top_reason.percentage >= FAILED_REASONS_CONCENTRATION_HIGH:
                    alerts.append(ErrorsAlert(
                        code="HIGH_FAILURE_CONCENTRATION",
                        title=f"Concentración extrema: {top_reason.reason}",
                        severity=AlertSeverity.HIGH,
                        metric="failure_concentration",
                        value=top_reason.percentage,
                        threshold=f">= {int(FAILED_REASONS_CONCENTRATION_HIGH * 100)}% en una razón",
                        time_scope="periodo",
                        recommended_action=f"El {int(top_reason.percentage * 100)}% de fallos son por '{top_reason.reason}'. Investigar causa raíz.",
                        details=f"Razón: {top_reason.reason}, Conteo: {top_reason.count}",
                    ))
                elif top_reason.percentage >= FAILED_REASONS_CONCENTRATION_WARN:
                    alerts.append(ErrorsAlert(
                        code="WARN_FAILURE_CONCENTRATION",
                        title=f"Concentración en: {top_reason.reason}",
                        severity=AlertSeverity.MEDIUM,
                        metric="failure_concentration",
                        value=top_reason.percentage,
                        threshold=f">= {int(FAILED_REASONS_CONCENTRATION_WARN * 100)}% en una razón",
                        time_scope="periodo",
                        recommended_action=f"Revisar por qué '{top_reason.reason}' es tan frecuente.",
                    ))
        
        return alerts
    
    def _apply_severity_suppression(self, alerts: List[ErrorsAlert]) -> List[ErrorsAlert]:
        """Suprime alertas LOW si hay HIGH o MEDIUM (regla de severidad única)."""
        has_high_or_medium = any(
            a.severity in (AlertSeverity.HIGH, AlertSeverity.MEDIUM) 
            for a in alerts
        )
        
        if has_high_or_medium:
            return [a for a in alerts if a.severity != AlertSeverity.LOW]
        
        return alerts


# Fin del archivo
