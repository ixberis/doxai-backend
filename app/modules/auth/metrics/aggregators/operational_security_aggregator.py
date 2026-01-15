# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/operational_security_aggregator.py

Agregador para métricas de seguridad operativa de Auth.

Fuentes de datos:
- public.login_attempts: intentos de login, fallos, fuerza bruta
- public.user_sessions: sesiones activas, múltiples sesiones
- public.password_resets: solicitudes, completadas, abandonadas
- public.auth_email_events: correos de password reset

Autor: Sistema
Fecha: 2026-01-05
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import List, Literal, Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Import canonical reason groupings
from app.modules.auth.enums.login_failure_reason_enum import (
    RATE_LIMIT_REASONS,
    LOCKOUT_REASONS,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Umbrales configurables (fuente de verdad)
# Regla de severidad:
#   - Cruza umbral "_high" ⇒ AlertSeverity.HIGH
#   - Cruza umbral "_warn" ⇒ AlertSeverity.MEDIUM
#   - Informativo (ej. >0) ⇒ AlertSeverity.LOW
# ─────────────────────────────────────────────────────────────────
HIGH_FAILURES_THRESHOLD = 5  # IPs/usuarios con más de N fallos

# Umbrales para alertas (warn = MEDIUM, high = HIGH)
# REGLA DE SEVERIDAD ÚNICA:
#   - valor >= umbral_high ⇒ AlertSeverity.HIGH
#   - valor >= umbral_warn ⇒ AlertSeverity.MEDIUM  
#   - valor > 0 (informativo) ⇒ AlertSeverity.LOW
LOGIN_FAILURE_RATE_WARN = 0.10  # 10% → MEDIUM
LOGIN_FAILURE_RATE_HIGH = 0.30  # 30% → HIGH
IPS_WITH_HIGH_FAILURES_WARN = 1  # ≥1 → MEDIUM
IPS_WITH_HIGH_FAILURES_HIGH = 10  # ≥10 → HIGH
USERS_WITH_HIGH_FAILURES_WARN = 1
USERS_WITH_HIGH_FAILURES_HIGH = 10
LOCKOUTS_TRIGGERED_WARN = 1
LOCKOUTS_TRIGGERED_HIGH = 5
RESET_REQUESTS_BY_USER_WARN = 1
RESET_REQUESTS_BY_USER_HIGH = 5
# Sesiones múltiples: ≥2 es normal (multi-dispositivo), ≥10 merece revisión
USERS_WITH_MULTIPLE_SESSIONS_WARN = 2  # ≥2 → MEDIUM (más de 1 sesión)
USERS_WITH_MULTIPLE_SESSIONS_HIGH = 10  # ≥10 → HIGH
SESSIONS_EXPIRING_WARN = 10
ACCOUNTS_LOCKED_WARN = 1
LOGIN_NO_SESSION_WARN = 3  # Usuarios con login exitoso pero sin sesión → MEDIUM
LOGIN_NO_SESSION_HIGH = 10  # → HIGH

# Legacy (mantener compatibilidad)
MULTIPLE_SESSIONS_THRESHOLD = 1
MULTIPLE_RESET_REQUESTS_THRESHOLD = 1


class AlertSeverity(str, Enum):
    """Niveles de severidad para alertas."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


from typing import Union

@dataclass
class SecurityAlert:
    """Estructura de una alerta de seguridad."""
    code: str  # Código estable, ej. HIGH_LOGIN_FAILURE_RATE
    title: str  # Título humano
    severity: AlertSeverity
    metric: str  # Nombre de la métrica
    value: Union[int, float]  # Conteos = int, ratios = float
    threshold: str  # Umbral como string descriptivo
    time_scope: Literal["periodo", "stock", "tiempo_real"]
    recommended_action: str  # 1-2 líneas
    details: Optional[str] = None  # Detalles adicionales


@dataclass
class SecurityThresholds:
    """Todos los umbrales usados (para frontend). Fuente de verdad."""
    high_failures: int = HIGH_FAILURES_THRESHOLD
    multiple_sessions: int = MULTIPLE_SESSIONS_THRESHOLD
    multiple_reset_requests: int = MULTIPLE_RESET_REQUESTS_THRESHOLD
    login_failure_rate_warn: float = LOGIN_FAILURE_RATE_WARN
    login_failure_rate_high: float = LOGIN_FAILURE_RATE_HIGH
    ips_with_high_failures_warn: int = IPS_WITH_HIGH_FAILURES_WARN
    ips_with_high_failures_high: int = IPS_WITH_HIGH_FAILURES_HIGH
    users_with_high_failures_warn: int = USERS_WITH_HIGH_FAILURES_WARN
    users_with_high_failures_high: int = USERS_WITH_HIGH_FAILURES_HIGH
    lockouts_triggered_warn: int = LOCKOUTS_TRIGGERED_WARN
    lockouts_triggered_high: int = LOCKOUTS_TRIGGERED_HIGH
    reset_requests_by_user_warn: int = RESET_REQUESTS_BY_USER_WARN
    reset_requests_by_user_high: int = RESET_REQUESTS_BY_USER_HIGH
    users_with_multiple_sessions_warn: int = USERS_WITH_MULTIPLE_SESSIONS_WARN
    users_with_multiple_sessions_high: int = USERS_WITH_MULTIPLE_SESSIONS_HIGH
    sessions_expiring_warn: int = SESSIONS_EXPIRING_WARN
    accounts_locked_warn: int = ACCOUNTS_LOCKED_WARN
    login_no_session_warn: int = LOGIN_NO_SESSION_WARN
    login_no_session_high: int = LOGIN_NO_SESSION_HIGH

    def to_dict(self) -> dict:
        """Convierte a diccionario para serialización."""
        return {
            "high_failures": self.high_failures,
            "multiple_sessions": self.multiple_sessions,
            "multiple_reset_requests": self.multiple_reset_requests,
            "login_failure_rate_warn": self.login_failure_rate_warn,
            "login_failure_rate_high": self.login_failure_rate_high,
            "ips_with_high_failures_warn": self.ips_with_high_failures_warn,
            "ips_with_high_failures_high": self.ips_with_high_failures_high,
            "users_with_high_failures_warn": self.users_with_high_failures_warn,
            "users_with_high_failures_high": self.users_with_high_failures_high,
            "lockouts_triggered_warn": self.lockouts_triggered_warn,
            "lockouts_triggered_high": self.lockouts_triggered_high,
            "reset_requests_by_user_warn": self.reset_requests_by_user_warn,
            "reset_requests_by_user_high": self.reset_requests_by_user_high,
            "users_with_multiple_sessions_warn": self.users_with_multiple_sessions_warn,
            "users_with_multiple_sessions_high": self.users_with_multiple_sessions_high,
            "sessions_expiring_warn": self.sessions_expiring_warn,
            "accounts_locked_warn": self.accounts_locked_warn,
            "login_no_session_warn": self.login_no_session_warn,
            "login_no_session_high": self.login_no_session_high,
        }


@dataclass
class MetricError:
    """Error al obtener una métrica específica."""
    name: str
    error_type: str
    message: str


@dataclass
class SecurityMetricsData:
    """Métricas de seguridad operativa."""
    
    # 1. Accesos (periodo)
    login_attempts_total: int = 0
    login_attempts_failed: int = 0
    login_attempts_success: int = 0
    login_failure_rate: Optional[float] = None
    
    # 2. Señales de fuerza bruta (periodo)
    ips_with_high_failures: int = 0
    users_with_high_failures: int = 0
    lockouts_triggered: int = 0
    accounts_locked_active: int = 0  # stock
    
    # 3. Sesiones (tiempo real + periodo)
    sessions_active: int = 0
    users_with_multiple_sessions: int = 0
    sessions_last_24h: int = 0
    sessions_expiring_24h: int = 0
    
    # 4. Password reset (periodo)
    password_reset_requests: int = 0
    password_reset_completed: int = 0
    password_reset_abandoned: int = 0
    reset_requests_by_user_gt_1: int = 0  # usuarios con >1 solicitud
    
    # 5. Indicadores de riesgo (derivados)
    users_with_failed_login_and_reset: int = 0
    accounts_with_login_but_no_recent_session: int = 0
    
    # Alertas
    alerts: List[SecurityAlert] = field(default_factory=list)
    alerts_high: int = 0
    alerts_medium: int = 0
    alerts_low: int = 0
    
    # Metadata
    from_date: str = ""
    to_date: str = ""
    generated_at: str = ""
    notes: List[str] = field(default_factory=list)
    
    # Errors (NO más fallback silencioso)
    errors: List[MetricError] = field(default_factory=list)
    partial: bool = False  # True si hay errores en métricas críticas
    
    # Umbrales completos (fuente de verdad para frontend)
    thresholds: SecurityThresholds = field(default_factory=SecurityThresholds)


class SecurityAggregator:
    """
    Agregador para métricas de seguridad del módulo Auth.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _build_range(self, from_date: date, to_date: date):
        """Construye rango half-open UTC."""
        from_ts = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        return from_ts, to_ts
    
    async def get_security_metrics(
        self,
        from_date: Optional[Union[str, date]] = None,
        to_date: Optional[Union[str, date]] = None,
    ) -> SecurityMetricsData:
        """
        Obtiene métricas de seguridad operativa.
        
        Args:
            from_date: Fecha inicio (str YYYY-MM-DD o date)
            to_date: Fecha fin (str YYYY-MM-DD o date)
        
        Returns:
            SecurityMetricsData con todas las métricas
        """
        # Default: últimos 7 días
        if not from_date or not to_date:
            today = datetime.now(timezone.utc).date()
            from_d = today - timedelta(days=7)
            to_d = today
        else:
            # Soportar str o date (patrón canónico temporal)
            if isinstance(from_date, str):
                from_d = datetime.strptime(from_date, "%Y-%m-%d").date()
            else:
                from_d = from_date
            
            if isinstance(to_date, str):
                to_d = datetime.strptime(to_date, "%Y-%m-%d").date()
            else:
                to_d = to_date
        
        from_ts, to_ts = self._build_range(from_d, to_d)
        
        logger.info(
            "get_security_metrics from=%s to=%s from_ts=%s to_ts=%s",
            from_d, to_d, from_ts, to_ts
        )
        
        notes = []
        errors: List[MetricError] = []
        
        # ─────────────────────────────────────────────────────────────
        # 1. ACCESOS (periodo)
        # ─────────────────────────────────────────────────────────────
        login_attempts_total = 0
        login_attempts_failed = 0
        login_attempts_success = 0
        login_failure_rate = None
        
        try:
            q = text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE success = false) as failed,
                    COUNT(*) FILTER (WHERE success = true) as success
                FROM public.login_attempts
                WHERE created_at >= :from_ts
                  AND created_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row:
                login_attempts_total = int(row.total or 0)
                login_attempts_failed = int(row.failed or 0)
                login_attempts_success = int(row.success or 0)
                if login_attempts_total > 0:
                    login_failure_rate = round(login_attempts_failed / login_attempts_total, 4)
        except Exception as e:
            logger.warning("login_attempts metrics failed: %s", e)
            notes.append("login_attempts: error de consulta")
            errors.append(MetricError(
                name="login_attempts",
                error_type=type(e).__name__,
                message=str(e)[:200],
            ))
        
        # ─────────────────────────────────────────────────────────────
        # 2. SEÑALES DE FUERZA BRUTA (periodo)
        # ─────────────────────────────────────────────────────────────
        ips_with_high_failures = 0
        users_with_high_failures = 0
        lockouts_triggered = 0
        accounts_locked_active = 0
        
        # IPs con muchos fallos
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT COUNT(DISTINCT ip_address)
                    FROM (
                        SELECT ip_address, COUNT(*) as cnt
                        FROM public.login_attempts
                        WHERE success = false
                          AND created_at >= :from_ts
                          AND created_at < :to_ts
                        GROUP BY ip_address
                        HAVING COUNT(*) > :threshold
                    ) sub
                """)
                res = await self.db.execute(q, {
                    "from_ts": from_ts,
                    "to_ts": to_ts,
                    "threshold": HIGH_FAILURES_THRESHOLD,
                })
                row = res.first()
                if row and row[0]:
                    ips_with_high_failures = int(row[0])
        except Exception as e:
            logger.debug("ips_with_high_failures failed: %s", e)
        
        # Usuarios con muchos fallos
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT COUNT(DISTINCT user_id)
                    FROM (
                        SELECT user_id, COUNT(*) as cnt
                        FROM public.login_attempts
                        WHERE success = false
                          AND user_id IS NOT NULL
                          AND created_at >= :from_ts
                          AND created_at < :to_ts
                        GROUP BY user_id
                        HAVING COUNT(*) > :threshold
                    ) sub
                """)
                res = await self.db.execute(q, {
                    "from_ts": from_ts,
                    "to_ts": to_ts,
                    "threshold": HIGH_FAILURES_THRESHOLD,
                })
                row = res.first()
                if row and row[0]:
                    users_with_high_failures = int(row[0])
        except Exception as e:
            logger.debug("users_with_high_failures failed: %s", e)
        
        # Lockouts triggered (both legacy and new reason values)
        # Uses canonical groupings: RATE_LIMIT_REASONS + LOCKOUT_REASONS
        # Uses CAST(:param AS text[]) for proper array binding with asyncpg
        try:
            async with self.db.begin_nested():
                all_lockout_reasons = list(RATE_LIMIT_REASONS | LOCKOUT_REASONS)
                q = text("""
                    SELECT COUNT(*)
                    FROM public.login_attempts
                    WHERE reason::text = ANY(CAST(:reasons AS text[]))
                      AND created_at >= :from_ts
                      AND created_at < :to_ts
                """)
                res = await self.db.execute(q, {
                    "reasons": all_lockout_reasons,
                    "from_ts": from_ts,
                    "to_ts": to_ts,
                })
                row = res.first()
                if row and row[0]:
                    lockouts_triggered = int(row[0])
        except Exception as e:
            logger.debug("lockouts_triggered failed: %s", e)
        
        # Cuentas bloqueadas activas (stock)
        # NOTA: Esta métrica requiere una tabla de lockouts con locked_until > now()
        # que actualmente no existe. Se reporta como no implementada.
        # El "lockout real" por rate limiting se mide con lockouts_triggered arriba.
        # NO usamos user_status porque 'suspended' es un estado administrativo diferente.
        accounts_locked_active = 0
        notes.append("accounts_locked_active: not implemented (no lockout source)")
        
        # ─────────────────────────────────────────────────────────────
        # 3. SESIONES (tiempo real + periodo)
        # ─────────────────────────────────────────────────────────────
        sessions_active = 0
        users_with_multiple_sessions = 0
        sessions_last_24h = 0
        sessions_expiring_24h = 0
        
        # Usar función SECURITY DEFINER para bypass RLS y obtener todas las métricas
        # en una sola llamada (más eficiente y sin problemas de RLS)
        import time as _time
        session_query_start = _time.perf_counter()
        
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT 
                        sessions_active,
                        users_with_multiple_sessions,
                        sessions_last_24h,
                        sessions_expiring_24h
                    FROM public.fn_metrics_sessions_all(:threshold)
                """)
                res = await self.db.execute(q, {"threshold": MULTIPLE_SESSIONS_THRESHOLD})
                row = res.first()
                session_query_ms = (_time.perf_counter() - session_query_start) * 1000
                
                if row:
                    sessions_active = int(row.sessions_active or 0)
                    users_with_multiple_sessions = int(row.users_with_multiple_sessions or 0)
                    sessions_last_24h = int(row.sessions_last_24h or 0)
                    sessions_expiring_24h = int(row.sessions_expiring_24h or 0)
                
                logger.info(
                    "session_metrics_query query_name=fn_metrics_sessions_all "
                    "duration_ms=%.2f sessions_active=%d users_multiple=%d "
                    "sessions_24h=%d expiring_24h=%d",
                    session_query_ms, sessions_active, users_with_multiple_sessions,
                    sessions_last_24h, sessions_expiring_24h
                )
            
        except Exception as e:
            session_query_ms = (_time.perf_counter() - session_query_start) * 1000
            logger.warning(
                "session_metrics_query FAILED query_name=fn_metrics_sessions_all "
                "duration_ms=%.2f error=%s",
                session_query_ms, str(e),
                exc_info=True
            )
            errors.append(MetricError(
                name="sessions_all",
                error_type=type(e).__name__,
                message=str(e)
            ))
            notes.append("sessions: error de consulta (RLS o función no disponible)")
        
        # ─────────────────────────────────────────────────────────────
        # 4. PASSWORD RESET (periodo)
        # ─────────────────────────────────────────────────────────────
        password_reset_requests = 0
        password_reset_completed = 0
        password_reset_abandoned = 0
        reset_requests_by_user_gt_1 = 0
        
        # Solicitudes de reset en periodo
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT COUNT(*)
                    FROM public.password_resets
                    WHERE created_at >= :from_ts
                      AND created_at < :to_ts
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0]:
                    password_reset_requests = int(row[0])
        except Exception as e:
            logger.debug("password_reset_requests failed: %s", e)
        
        # Resets completados en periodo
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT COUNT(*)
                    FROM public.password_resets
                    WHERE used_at >= :from_ts
                      AND used_at < :to_ts
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0]:
                    password_reset_completed = int(row[0])
        except Exception as e:
            logger.debug("password_reset_completed failed: %s", e)
        
        # Abandonados: creados en periodo pero no usados y expirados
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT COUNT(*)
                    FROM public.password_resets
                    WHERE created_at >= :from_ts
                      AND created_at < :to_ts
                      AND used_at IS NULL
                      AND expires_at < NOW()
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0]:
                    password_reset_abandoned = int(row[0])
        except Exception as e:
            logger.debug("password_reset_abandoned failed: %s", e)
        
        # Usuarios con >1 solicitud en periodo
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT user_id, COUNT(*) as cnt
                        FROM public.password_resets
                        WHERE created_at >= :from_ts
                          AND created_at < :to_ts
                        GROUP BY user_id
                        HAVING COUNT(*) > :threshold
                    ) sub
                """)
                res = await self.db.execute(q, {
                    "from_ts": from_ts,
                    "to_ts": to_ts,
                    "threshold": MULTIPLE_RESET_REQUESTS_THRESHOLD,
                })
                row = res.first()
                if row and row[0]:
                    reset_requests_by_user_gt_1 = int(row[0])
        except Exception as e:
            logger.debug("reset_requests_by_user_gt_1 failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 5. INDICADORES DE RIESGO (derivados)
        # ─────────────────────────────────────────────────────────────
        users_with_failed_login_and_reset = 0
        accounts_with_login_but_no_recent_session = 0
        
        # Usuarios con login fallido Y solicitud de reset en el periodo
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT COUNT(DISTINCT la.user_id)
                    FROM public.login_attempts la
                    INNER JOIN public.password_resets pr ON la.user_id = pr.user_id
                    WHERE la.success = false
                      AND la.created_at >= :from_ts
                      AND la.created_at < :to_ts
                      AND pr.created_at >= :from_ts
                      AND pr.created_at < :to_ts
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0]:
                    users_with_failed_login_and_reset = int(row[0])
        except Exception as e:
            logger.debug("users_with_failed_login_and_reset failed: %s", e)
        
        # Cuentas con login exitoso en periodo pero sin sesión activa ahora
        try:
            async with self.db.begin_nested():
                q = text("""
                    SELECT COUNT(DISTINCT la.user_id)
                    FROM public.login_attempts la
                    WHERE la.success = true
                      AND la.created_at >= :from_ts
                      AND la.created_at < :to_ts
                      AND la.user_id NOT IN (
                          SELECT user_id FROM public.user_sessions
                          WHERE expires_at > NOW()
                            AND revoked_at IS NULL
                      )
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0]:
                    accounts_with_login_but_no_recent_session = int(row[0])
        except Exception as e:
            logger.debug("accounts_with_login_but_no_recent_session failed: %s", e)
        
        generated_at = datetime.now(timezone.utc).isoformat()
        
        # ─────────────────────────────────────────────────────────────
        # CONSTRUIR ALERTAS
        # ─────────────────────────────────────────────────────────────
        alerts: List[SecurityAlert] = []
        thresholds = SecurityThresholds()
        
        # 1. Login failure rate
        if login_failure_rate is not None:
            if login_failure_rate > thresholds.login_failure_rate_high:
                alerts.append(SecurityAlert(
                    code="HIGH_LOGIN_FAILURE_RATE",
                    title="Tasa de fallo de login muy alta",
                    severity=AlertSeverity.HIGH,
                    metric="login_failure_rate",
                    value=login_failure_rate,
                    threshold=f">{thresholds.login_failure_rate_high * 100:.0f}%",
                    time_scope="periodo",
                    recommended_action="Revisar IPs y usuarios con más fallos. Posible ataque de fuerza bruta.",
                ))
            elif login_failure_rate > thresholds.login_failure_rate_warn:
                alerts.append(SecurityAlert(
                    code="WARN_LOGIN_FAILURE_RATE",
                    title="Tasa de fallo de login elevada",
                    severity=AlertSeverity.MEDIUM,
                    metric="login_failure_rate",
                    value=login_failure_rate,
                    threshold=f">{thresholds.login_failure_rate_warn * 100:.0f}%",
                    time_scope="periodo",
                    recommended_action="Monitorear tendencia. Puede indicar problemas de UX o credenciales olvidadas.",
                ))
        
        # 2. IPs con muchos fallos
        if ips_with_high_failures >= thresholds.ips_with_high_failures_high:
            alerts.append(SecurityAlert(
                code="HIGH_SUSPICIOUS_IPS",
                title="Muchas IPs sospechosas",
                severity=AlertSeverity.HIGH,
                metric="ips_with_high_failures",
                value=ips_with_high_failures,
                threshold=f"≥{thresholds.ips_with_high_failures_high}",
                time_scope="periodo",
                recommended_action="Revisar IPs para posible bloqueo. Probable ataque distribuido.",
            ))
        elif ips_with_high_failures >= thresholds.ips_with_high_failures_warn:
            alerts.append(SecurityAlert(
                code="WARN_SUSPICIOUS_IPS",
                title="IPs con actividad sospechosa",
                severity=AlertSeverity.MEDIUM,
                metric="ips_with_high_failures",
                value=ips_with_high_failures,
                threshold=f"≥{thresholds.ips_with_high_failures_warn}",
                time_scope="periodo",
                recommended_action="Monitorear estas IPs. Puede ser usuario legítimo con problemas.",
            ))
        
        # 3. Usuarios con muchos fallos
        if users_with_high_failures >= thresholds.users_with_high_failures_high:
            alerts.append(SecurityAlert(
                code="HIGH_SUSPICIOUS_USERS",
                title="Muchos usuarios con fallos repetidos",
                severity=AlertSeverity.HIGH,
                metric="users_with_high_failures",
                value=users_with_high_failures,
                threshold=f"≥{thresholds.users_with_high_failures_high}",
                time_scope="periodo",
                recommended_action="Verificar si son cuentas comprometidas o ataques dirigidos.",
            ))
        elif users_with_high_failures >= thresholds.users_with_high_failures_warn:
            alerts.append(SecurityAlert(
                code="WARN_SUSPICIOUS_USERS",
                title="Usuarios con múltiples fallos",
                severity=AlertSeverity.MEDIUM,
                metric="users_with_high_failures",
                value=users_with_high_failures,
                threshold=f"≥{thresholds.users_with_high_failures_warn}",
                time_scope="periodo",
                recommended_action="Revisar si necesitan reset de contraseña.",
            ))
        
        # 4. Lockouts
        if lockouts_triggered >= thresholds.lockouts_triggered_high:
            alerts.append(SecurityAlert(
                code="HIGH_LOCKOUTS",
                title="Muchos bloqueos de cuenta",
                severity=AlertSeverity.HIGH,
                metric="lockouts_triggered",
                value=lockouts_triggered,
                threshold=f"≥{thresholds.lockouts_triggered_high}",
                time_scope="periodo",
                recommended_action="Revisar si es ataque o problema sistémico. Considerar ajustar umbrales.",
            ))
        elif lockouts_triggered >= thresholds.lockouts_triggered_warn:
            alerts.append(SecurityAlert(
                code="WARN_LOCKOUTS",
                title="Bloqueos de cuenta detectados",
                severity=AlertSeverity.MEDIUM,
                metric="lockouts_triggered",
                value=lockouts_triggered,
                threshold=f"≥{thresholds.lockouts_triggered_warn}",
                time_scope="periodo",
                recommended_action="Revisar usuarios afectados para desbloqueo si es necesario.",
            ))
        
        # 5. Cuentas bloqueadas (stock)
        if accounts_locked_active >= thresholds.accounts_locked_warn:
            alerts.append(SecurityAlert(
                code="WARN_ACCOUNTS_LOCKED",
                title="Cuentas actualmente bloqueadas",
                severity=AlertSeverity.MEDIUM,
                metric="accounts_locked_active",
                value=accounts_locked_active,
                threshold=f"≥{thresholds.accounts_locked_warn}",
                time_scope="stock",
                recommended_action="Revisar cuentas bloqueadas y desbloquear si corresponde.",
            ))
        
        # 6. Usuarios con múltiples sesiones
        # REGLA ÚNICA: _high → HIGH, _warn → MEDIUM
        if users_with_multiple_sessions >= thresholds.users_with_multiple_sessions_high:
            alerts.append(SecurityAlert(
                code="HIGH_MULTIPLE_SESSIONS",
                title="Muchos usuarios con múltiples sesiones",
                severity=AlertSeverity.HIGH,  # _high → HIGH (regla única)
                metric="users_with_multiple_sessions",
                value=users_with_multiple_sessions,
                threshold=f"≥{thresholds.users_with_multiple_sessions_high}",
                time_scope="tiempo_real",
                recommended_action="Revisar posible compartición masiva de cuentas.",
            ))
        elif users_with_multiple_sessions >= thresholds.users_with_multiple_sessions_warn:
            alerts.append(SecurityAlert(
                code="WARN_MULTIPLE_SESSIONS",
                title="Usuarios con múltiples sesiones",
                severity=AlertSeverity.MEDIUM,  # _warn → MEDIUM
                metric="users_with_multiple_sessions",
                value=users_with_multiple_sessions,
                threshold=f"≥{thresholds.users_with_multiple_sessions_warn}",
                time_scope="tiempo_real",
                recommended_action="Monitorear. Puede ser uso legítimo multi-dispositivo.",
            ))
        
        # 7. Sesiones expirando (informativo)
        if sessions_expiring_24h >= thresholds.sessions_expiring_warn:
            alerts.append(SecurityAlert(
                code="INFO_SESSIONS_EXPIRING",
                title="Sesiones próximas a expirar",
                severity=AlertSeverity.LOW,
                metric="sessions_expiring_24h",
                value=sessions_expiring_24h,
                threshold=f"≥{thresholds.sessions_expiring_warn}",
                time_scope="tiempo_real",
                recommended_action="Informativo. Los usuarios deberán re-autenticarse.",
            ))
        
        # 8. Reset requests por usuario
        # REGLA ÚNICA: _high → HIGH, _warn → MEDIUM
        if reset_requests_by_user_gt_1 >= thresholds.reset_requests_by_user_high:
            alerts.append(SecurityAlert(
                code="HIGH_MULTIPLE_RESETS",
                title="Muchos usuarios con múltiples resets",
                severity=AlertSeverity.HIGH,  # _high → HIGH
                metric="reset_requests_by_user_gt_1",
                value=reset_requests_by_user_gt_1,
                threshold=f"≥{thresholds.reset_requests_by_user_high}",
                time_scope="periodo",
                recommended_action="Revisar entregas de correo. Posible problema de deliverability.",
            ))
        elif reset_requests_by_user_gt_1 >= thresholds.reset_requests_by_user_warn:
            alerts.append(SecurityAlert(
                code="WARN_MULTIPLE_RESETS",
                title="Usuarios con múltiples solicitudes de reset",
                severity=AlertSeverity.MEDIUM,  # _warn → MEDIUM
                metric="reset_requests_by_user_gt_1",
                value=reset_requests_by_user_gt_1,
                threshold=f"≥{thresholds.reset_requests_by_user_warn}",
                time_scope="periodo",
                recommended_action="Verificar si correos llegan correctamente.",
            ))
        
        # 9. Usuarios con fallo + reset (patrón normal de recuperación) → LOW
        if users_with_failed_login_and_reset > 0:
            alerts.append(SecurityAlert(
                code="INFO_FAILED_AND_RESET",
                title="Usuarios con fallo de login y reset",
                severity=AlertSeverity.LOW,
                metric="users_with_failed_login_and_reset",
                value=users_with_failed_login_and_reset,
                threshold="≥1",
                time_scope="periodo",
                recommended_action="Patrón normal de recuperación de cuenta. Monitorear si es frecuente.",
            ))
        
        # 10. Login exitoso sin sesión activa
        # REGLA ÚNICA: _high → HIGH, _warn → MEDIUM
        if accounts_with_login_but_no_recent_session >= thresholds.login_no_session_high:
            alerts.append(SecurityAlert(
                code="HIGH_LOGIN_NO_SESSION",
                title="Muchos logins exitosos sin sesión activa",
                severity=AlertSeverity.HIGH,
                metric="accounts_with_login_but_no_recent_session",
                value=accounts_with_login_but_no_recent_session,
                threshold=f"≥{thresholds.login_no_session_high}",
                time_scope="periodo",
                recommended_action="Revisar urgentemente. Posible problema de creación de sesión o ataque.",
            ))
        elif accounts_with_login_but_no_recent_session >= thresholds.login_no_session_warn:
            alerts.append(SecurityAlert(
                code="WARN_LOGIN_NO_SESSION",
                title="Logins exitosos sin sesión activa",
                severity=AlertSeverity.MEDIUM,
                metric="accounts_with_login_but_no_recent_session",
                value=accounts_with_login_but_no_recent_session,
                threshold=f"≥{thresholds.login_no_session_warn}",
                time_scope="periodo",
                recommended_action="Revisar si hay problemas de creación de sesión.",
            ))
        
        # Contar por severidad
        alerts_high = sum(1 for a in alerts if a.severity == AlertSeverity.HIGH)
        alerts_medium = sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM)
        alerts_low = sum(1 for a in alerts if a.severity == AlertSeverity.LOW)
        
        # ─────────────────────────────────────────────────────────────
        # LOG ESTRUCTURADO PARA OBSERVABILIDAD FUTURA
        # Campos para integración con Prometheus/Grafana/SIEM:
        # - alerts_codes: lista de códigos de alerta activos
        # - max_severity: severidad máxima ("high"|"medium"|"low"|None)
        # ─────────────────────────────────────────────────────────────
        alerts_codes = [a.code for a in alerts]
        max_severity: Optional[str] = None
        if alerts_high > 0:
            max_severity = "high"
        elif alerts_medium > 0:
            max_severity = "medium"
        elif alerts_low > 0:
            max_severity = "low"
        
        observability_log = {
            "event_type": "security_metrics_generated",
            "from_date": from_d.isoformat(),
            "to_date": to_d.isoformat(),
            "alerts_high": alerts_high,
            "alerts_medium": alerts_medium,
            "alerts_low": alerts_low,
            "alerts_codes": alerts_codes,
            "max_severity": max_severity,
            "login_attempts_total": login_attempts_total,
            "login_failure_rate": login_failure_rate,
            "ips_with_high_failures": ips_with_high_failures,
            "users_with_high_failures": users_with_high_failures,
            "lockouts_triggered": lockouts_triggered,
            "sessions_active": sessions_active,
            "password_reset_requests": password_reset_requests,
            "generated_at": generated_at,
        }
        logger.info("security_metrics_observability %s", json.dumps(observability_log))
        
        return SecurityMetricsData(
            # Accesos
            login_attempts_total=login_attempts_total,
            login_attempts_failed=login_attempts_failed,
            login_attempts_success=login_attempts_success,
            login_failure_rate=login_failure_rate,
            # Fuerza bruta
            ips_with_high_failures=ips_with_high_failures,
            users_with_high_failures=users_with_high_failures,
            lockouts_triggered=lockouts_triggered,
            accounts_locked_active=accounts_locked_active,
            # Sesiones
            sessions_active=sessions_active,
            users_with_multiple_sessions=users_with_multiple_sessions,
            sessions_last_24h=sessions_last_24h,
            sessions_expiring_24h=sessions_expiring_24h,
            # Password reset
            password_reset_requests=password_reset_requests,
            password_reset_completed=password_reset_completed,
            password_reset_abandoned=password_reset_abandoned,
            reset_requests_by_user_gt_1=reset_requests_by_user_gt_1,
            # Riesgo
            users_with_failed_login_and_reset=users_with_failed_login_and_reset,
            accounts_with_login_but_no_recent_session=accounts_with_login_but_no_recent_session,
            # Alertas
            alerts=alerts,
            alerts_high=alerts_high,
            alerts_medium=alerts_medium,
            alerts_low=alerts_low,
            # Metadata
            from_date=from_d.isoformat(),
            to_date=to_d.isoformat(),
            generated_at=generated_at,
            notes=notes,
            # Errors (NO más fallback silencioso)
            errors=errors,
            partial=len(errors) > 0,
            thresholds=thresholds,
        )


# Fin del archivo
