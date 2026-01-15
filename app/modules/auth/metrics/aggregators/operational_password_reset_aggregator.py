# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/operational_password_reset_aggregator.py

Agregador para métricas operativas de password reset de Auth.

Fuentes de datos:
- public.password_resets: tokens de reset, estados
- public.auth_email_events: emails enviados (instrumentado)
- public.app_users: usuarios

Autor: Sistema
Fecha: 2026-01-06
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import List, Literal, Optional, Union

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Umbrales configurables (fuente de verdad)
# Regla de severidad ÚNICA:
#   - Cruza umbral "_high" ⇒ AlertSeverity.HIGH
#   - Cruza umbral "_warn" ⇒ AlertSeverity.MEDIUM
#   - Informativo (ej. >0) ⇒ AlertSeverity.LOW (solo si no hay warn/high)
# ─────────────────────────────────────────────────────────────────

# Tokens expirados sin usar
RESET_EXPIRATIONS_WARN = 3  # ≥3 → MEDIUM
RESET_EXPIRATIONS_HIGH = 10  # ≥10 → HIGH

# Tasa de fallo de reset (1 - completed/sent)
RESET_FAILURE_RATE_WARN = 0.30  # 30% fallos → MEDIUM  
RESET_FAILURE_RATE_HIGH = 0.50  # 50% fallos → HIGH

# Tiempo promedio de reset (segundos)
# Más de 24h promedio es preocupante
SLOW_RESET_WARN = 86400  # 24h → MEDIUM
SLOW_RESET_HIGH = 172800  # 48h → HIGH

# Múltiples solicitudes por usuario
MULTIPLE_REQUESTS_WARN = 3  # ≥3 → MEDIUM
MULTIPLE_REQUESTS_HIGH = 10  # ≥10 → HIGH

# Pendientes de reset (>24h sin usar)
PENDING_RESETS_WARN = 5  # ≥5 → MEDIUM
PENDING_RESETS_HIGH = 20  # ≥20 → HIGH


class AlertSeverity(str, Enum):
    """Niveles de severidad para alertas."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class PasswordResetAlert:
    """Estructura de una alerta de password reset."""
    code: str  # Código estable, ej. HIGH_RESET_EXPIRATIONS
    title: str  # Título humano
    severity: AlertSeverity
    metric: str  # Nombre de la métrica
    value: Union[int, float]  # Conteos = int, ratios = float
    threshold: str  # Umbral como string descriptivo
    time_scope: Literal["periodo", "stock", "tiempo_real"]
    recommended_action: str  # 1-2 líneas para NO técnicos
    details: Optional[str] = None  # Detalles adicionales


@dataclass
class PasswordResetThresholds:
    """Todos los umbrales usados (para frontend). Fuente de verdad."""
    expirations_warn: int = RESET_EXPIRATIONS_WARN
    expirations_high: int = RESET_EXPIRATIONS_HIGH
    failure_rate_warn: float = RESET_FAILURE_RATE_WARN
    failure_rate_high: float = RESET_FAILURE_RATE_HIGH
    slow_reset_warn: int = SLOW_RESET_WARN
    slow_reset_high: int = SLOW_RESET_HIGH
    multiple_requests_warn: int = MULTIPLE_REQUESTS_WARN
    multiple_requests_high: int = MULTIPLE_REQUESTS_HIGH
    pending_24h_warn: int = PENDING_RESETS_WARN
    pending_24h_high: int = PENDING_RESETS_HIGH

    def to_dict(self) -> dict:
        """Convierte a diccionario para serialización."""
        return {
            "expirations_warn": self.expirations_warn,
            "expirations_high": self.expirations_high,
            "failure_rate_warn": self.failure_rate_warn,
            "failure_rate_high": self.failure_rate_high,
            "slow_reset_warn": self.slow_reset_warn,
            "slow_reset_high": self.slow_reset_high,
            "multiple_requests_warn": self.multiple_requests_warn,
            "multiple_requests_high": self.multiple_requests_high,
            "pending_24h_warn": self.pending_24h_warn,
            "pending_24h_high": self.pending_24h_high,
        }


@dataclass
class PasswordResetOperationalData:
    """Métricas operativas de password reset."""
    
    # Periodo
    password_reset_requests: int = 0
    password_reset_emails_sent: int = 0
    password_reset_completed: int = 0
    password_reset_expired: int = 0
    avg_time_to_reset_seconds: Optional[float] = None
    
    # Calidad / Pendientes
    pending_tokens_stock_24h: int = 0
    pending_created_in_period_24h: int = 0
    users_with_multiple_requests: int = 0
    
    # Stock (estado actual)
    password_reset_tokens_active: int = 0
    password_reset_tokens_expired_stock: int = 0
    
    # Tasa de fallo
    password_reset_failure_rate: Optional[float] = None
    
    # Alertas
    alerts: List[PasswordResetAlert] = field(default_factory=list)
    alerts_high: int = 0
    alerts_medium: int = 0
    alerts_low: int = 0
    
    # Metadata
    from_date: str = ""
    to_date: str = ""
    generated_at: str = ""
    notes: List[str] = field(default_factory=list)
    
    # Umbrales completos (fuente de verdad para frontend)
    thresholds: PasswordResetThresholds = field(default_factory=PasswordResetThresholds)
    
    # Trazabilidad
    email_events_source: str = "none"  # instrumented | fallback | none
    email_events_partial: bool = False  # True si source=='fallback'
    resends_instrumented: bool = False


class PasswordResetOperationalAggregator:
    """
    Agregador para métricas operativas de password reset.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _build_range(self, from_date: date, to_date: date):
        """Construye rango half-open UTC."""
        from_ts = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        return from_ts, to_ts
    
    async def get_password_reset_operational_metrics(
        self,
        from_date: Optional[Union[str, date]] = None,
        to_date: Optional[Union[str, date]] = None,
    ) -> PasswordResetOperationalData:
        """
        Obtiene métricas operativas de password reset.
        
        Args:
            from_date: Fecha inicio YYYY-MM-DD o date (opcional)
            to_date: Fecha fin YYYY-MM-DD o date (opcional)
        
        Returns:
            PasswordResetOperationalData con todas las métricas y alertas
        """
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
        now_ts = datetime.now(timezone.utc)
        threshold_24h = now_ts - timedelta(hours=24)
        
        logger.info(
            "get_password_reset_operational_metrics from=%s to=%s from_ts=%s to_ts=%s",
            from_d, to_d, from_ts, to_ts
        )
        
        notes: List[str] = []
        email_events_source = "none"
        email_events_partial = False
        resends_instrumented = False
        
        # ─────────────────────────────────────────────────────────────
        # 1. SOLICITUDES DE RESET (periodo) - desde password_resets
        # ─────────────────────────────────────────────────────────────
        password_reset_requests = 0
        
        try:
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
        
        # ─────────────────────────────────────────────────────────────
        # 2. EMAILS ENVIADOS (periodo) - Preferir auth_email_events
        # ─────────────────────────────────────────────────────────────
        password_reset_emails_sent = 0
        instrumented_count = 0
        
        # Intentar fuente instrumentada primero
        try:
            # Usar valor canónico 'password_reset' (alineado con SQL auth_email_type)
            q = text("""
                SELECT COUNT(*)
                FROM public.auth_email_events
                WHERE email_type = 'password_reset'
                  AND status = 'sent'
                  AND created_at >= :from_ts
                  AND created_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                instrumented_count = int(row[0])
        except Exception as e:
            logger.debug("auth_email_events query failed: %s", e)
        
        # Decisión robusta de source
        if instrumented_count > 0:
            password_reset_emails_sent = instrumented_count
            email_events_source = "instrumented"
        else:
            # Fallback: usar password_resets.created_at como proxy de email enviado
            password_reset_emails_sent = password_reset_requests
            if password_reset_requests > 0:
                email_events_source = "fallback"
                email_events_partial = True
                notes.append("Parcial (fallback): emails estimados desde solicitudes; tasa de fallo no disponible.")
        
        # ─────────────────────────────────────────────────────────────
        # 3. RESETS COMPLETADOS (periodo)
        # ─────────────────────────────────────────────────────────────
        password_reset_completed = 0
        
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.password_resets
                WHERE used_at IS NOT NULL
                  AND used_at >= :from_ts
                  AND used_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                password_reset_completed = int(row[0])
        except Exception as e:
            logger.debug("password_reset_completed failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 4. TOKENS EXPIRADOS (periodo)
        # Usar: expires_at en rango Y used_at IS NULL Y expires_at < NOW()
        # ─────────────────────────────────────────────────────────────
        password_reset_expired = 0
        
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.password_resets
                WHERE used_at IS NULL
                  AND expires_at >= :from_ts
                  AND expires_at < :to_ts
                  AND expires_at < :now_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts, "now_ts": now_ts})
            row = res.first()
            if row and row[0]:
                password_reset_expired = int(row[0])
        except Exception as e:
            logger.debug("password_reset_expired failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 5. USUARIOS CON MÚLTIPLES SOLICITUDES (periodo)
        # ─────────────────────────────────────────────────────────────
        users_with_multiple_requests = 0
        
        try:
            q = text("""
                SELECT COUNT(*) FROM (
                    SELECT user_id
                    FROM public.password_resets
                    WHERE created_at >= :from_ts
                      AND created_at < :to_ts
                    GROUP BY user_id
                    HAVING COUNT(*) > 1
                ) sub
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                users_with_multiple_requests = int(row[0])
        except Exception as e:
            logger.debug("users_with_multiple_requests failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 6. TIEMPO PROMEDIO DE RESET (periodo)
        # ─────────────────────────────────────────────────────────────
        avg_time_to_reset_seconds: Optional[float] = None
        
        try:
            q = text("""
                SELECT AVG(EXTRACT(EPOCH FROM (used_at - created_at)))
                FROM public.password_resets
                WHERE used_at IS NOT NULL
                  AND used_at >= :from_ts
                  AND used_at < :to_ts
                  AND used_at > created_at
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                avg_time_to_reset_seconds = round(float(row[0]), 2)
        except Exception as e:
            logger.debug("avg_time_to_reset failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 7. PENDIENTES >24H - Separar STOCK vs PERIODO
        # ─────────────────────────────────────────────────────────────
        pending_tokens_stock_24h = 0
        pending_created_in_period_24h = 0
        
        # Stock: tokens vigentes (expires_at > now), creados hace >24h, sin usar
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.password_resets
                WHERE used_at IS NULL
                  AND expires_at > :now_ts
                  AND created_at < :threshold_24h
            """)
            res = await self.db.execute(q, {"now_ts": now_ts, "threshold_24h": threshold_24h})
            row = res.first()
            if row and row[0]:
                pending_tokens_stock_24h = int(row[0])
        except Exception as e:
            logger.debug("pending_tokens_stock_24h failed: %s", e)
        
        # Periodo: creados en [from_ts, to_ts), que ya pasaron 24h sin usar, y siguen vigentes
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.password_resets
                WHERE used_at IS NULL
                  AND created_at >= :from_ts
                  AND created_at < :to_ts
                  AND created_at < :threshold_24h
                  AND expires_at > :now_ts
            """)
            res = await self.db.execute(q, {
                "from_ts": from_ts, 
                "to_ts": to_ts, 
                "threshold_24h": threshold_24h,
                "now_ts": now_ts,
            })
            row = res.first()
            if row and row[0]:
                pending_created_in_period_24h = int(row[0])
        except Exception as e:
            logger.debug("pending_created_in_period_24h failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 8. STOCK: tokens activos y expirados (histórico)
        # ─────────────────────────────────────────────────────────────
        password_reset_tokens_active = 0
        password_reset_tokens_expired_stock = 0
        
        # Tokens activos: expires_at > now AND used_at IS NULL
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.password_resets
                WHERE used_at IS NULL
                  AND expires_at > :now_ts
            """)
            res = await self.db.execute(q, {"now_ts": now_ts})
            row = res.first()
            if row and row[0]:
                password_reset_tokens_active = int(row[0])
        except Exception as e:
            logger.debug("password_reset_tokens_active failed: %s", e)
        
        # Tokens expirados (histórico): expires_at < now AND used_at IS NULL
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.password_resets
                WHERE used_at IS NULL
                  AND expires_at < :now_ts
            """)
            res = await self.db.execute(q, {"now_ts": now_ts})
            row = res.first()
            if row and row[0]:
                password_reset_tokens_expired_stock = int(row[0])
        except Exception as e:
            logger.debug("password_reset_tokens_expired_stock failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 9. TASA DE FALLO - Solo si NO es fallback (evitar tasas engañosas)
        # ─────────────────────────────────────────────────────────────
        password_reset_failure_rate: Optional[float] = None
        
        # REGLA: No calcular tasa si datos son parciales (fallback)
        if email_events_source == "instrumented" and password_reset_emails_sent > 0:
            password_reset_failure_rate = round(
                1 - (password_reset_completed / password_reset_emails_sent), 4
            )
            # Clamp to [0, 1]
            if password_reset_failure_rate < 0:
                password_reset_failure_rate = 0.0
            if password_reset_failure_rate > 1:
                password_reset_failure_rate = 1.0
        
        # ─────────────────────────────────────────────────────────────
        # 10. GENERAR ALERTAS
        # ─────────────────────────────────────────────────────────────
        alerts: List[PasswordResetAlert] = []
        thresholds = PasswordResetThresholds()
        
        # 10.1 Tokens expirados
        if password_reset_expired >= thresholds.expirations_high:
            alerts.append(PasswordResetAlert(
                code="HIGH_RESET_EXPIRATIONS",
                title="Muchos usuarios no usaron su enlace de recuperación",
                severity=AlertSeverity.HIGH,
                metric="password_reset_expired",
                value=password_reset_expired,
                threshold=f"≥{thresholds.expirations_high}",
                time_scope="periodo",
                recommended_action="Revisar si los correos de recuperación llegan correctamente y si el enlace es claro.",
            ))
        elif password_reset_expired >= thresholds.expirations_warn:
            alerts.append(PasswordResetAlert(
                code="WARN_RESET_EXPIRATIONS",
                title="Algunos usuarios no usaron su enlace de recuperación",
                severity=AlertSeverity.MEDIUM,
                metric="password_reset_expired",
                value=password_reset_expired,
                threshold=f"≥{thresholds.expirations_warn}",
                time_scope="periodo",
                recommended_action="Monitorear si los correos llegan y el tiempo de vida del enlace es suficiente.",
            ))
        
        # 10.2 Tasa de fallo
        if password_reset_failure_rate is not None:
            if password_reset_failure_rate >= thresholds.failure_rate_high:
                alerts.append(PasswordResetAlert(
                    code="HIGH_RESET_FAILURE_RATE",
                    title="Tasa de recuperación muy baja",
                    severity=AlertSeverity.HIGH,
                    metric="password_reset_failure_rate",
                    value=password_reset_failure_rate,
                    threshold=f"≥{int(thresholds.failure_rate_high * 100)}%",
                    time_scope="periodo",
                    recommended_action="Investigar por qué los usuarios no completan el proceso de recuperación.",
                ))
            elif password_reset_failure_rate >= thresholds.failure_rate_warn:
                alerts.append(PasswordResetAlert(
                    code="WARN_RESET_FAILURE_RATE",
                    title="Tasa de recuperación baja",
                    severity=AlertSeverity.MEDIUM,
                    metric="password_reset_failure_rate",
                    value=password_reset_failure_rate,
                    threshold=f"≥{int(thresholds.failure_rate_warn * 100)}%",
                    time_scope="periodo",
                    recommended_action="Revisar el flujo de recuperación de contraseña.",
                ))
        
        # 10.3 Tiempo lento
        if avg_time_to_reset_seconds is not None:
            if avg_time_to_reset_seconds >= thresholds.slow_reset_high:
                alerts.append(PasswordResetAlert(
                    code="HIGH_SLOW_RESET",
                    title="Tiempo de recuperación muy elevado",
                    severity=AlertSeverity.HIGH,
                    metric="avg_time_to_reset_seconds",
                    value=avg_time_to_reset_seconds,
                    threshold=f"≥{thresholds.slow_reset_high // 3600}h",
                    time_scope="periodo",
                    recommended_action="Los usuarios tardan mucho en usar el enlace. Revisar UX del correo.",
                ))
            elif avg_time_to_reset_seconds >= thresholds.slow_reset_warn:
                alerts.append(PasswordResetAlert(
                    code="WARN_SLOW_RESET",
                    title="Tiempo de recuperación elevado",
                    severity=AlertSeverity.MEDIUM,
                    metric="avg_time_to_reset_seconds",
                    value=avg_time_to_reset_seconds,
                    threshold=f"≥{thresholds.slow_reset_warn // 3600}h",
                    time_scope="periodo",
                    recommended_action="Monitorear si los usuarios encuentran el correo fácilmente.",
                ))
        
        # 10.4 Múltiples solicitudes
        if users_with_multiple_requests >= thresholds.multiple_requests_high:
            alerts.append(PasswordResetAlert(
                code="HIGH_MULTIPLE_REQUESTS",
                title="Muchos usuarios solicitando múltiples recuperaciones",
                severity=AlertSeverity.HIGH,
                metric="users_with_multiple_requests",
                value=users_with_multiple_requests,
                threshold=f"≥{thresholds.multiple_requests_high}",
                time_scope="periodo",
                recommended_action="Revisar si hay problemas con la entrega de correos o el proceso.",
            ))
        elif users_with_multiple_requests >= thresholds.multiple_requests_warn:
            alerts.append(PasswordResetAlert(
                code="WARN_MULTIPLE_REQUESTS",
                title="Usuarios solicitando múltiples recuperaciones",
                severity=AlertSeverity.MEDIUM,
                metric="users_with_multiple_requests",
                value=users_with_multiple_requests,
                threshold=f"≥{thresholds.multiple_requests_warn}",
                time_scope="periodo",
                recommended_action="Verificar que los correos llegan correctamente.",
            ))
        
        # 10.5 Pendientes >24h (stock)
        if pending_tokens_stock_24h >= thresholds.pending_24h_high:
            alerts.append(PasswordResetAlert(
                code="HIGH_PENDING_RESETS",
                title="Muchos enlaces de recuperación sin usar (>24h)",
                severity=AlertSeverity.HIGH,
                metric="pending_tokens_stock_24h",
                value=pending_tokens_stock_24h,
                threshold=f"≥{thresholds.pending_24h_high}",
                time_scope="stock",
                recommended_action="Revisar por qué los usuarios no usan los enlaces de recuperación.",
            ))
        elif pending_tokens_stock_24h >= thresholds.pending_24h_warn:
            alerts.append(PasswordResetAlert(
                code="WARN_PENDING_RESETS",
                title="Enlaces de recuperación sin usar (>24h)",
                severity=AlertSeverity.MEDIUM,
                metric="pending_tokens_stock_24h",
                value=pending_tokens_stock_24h,
                threshold=f"≥{thresholds.pending_24h_warn}",
                time_scope="stock",
                recommended_action="Monitorear si el proceso de recuperación es claro.",
            ))
        
        # Conteo de alertas por severidad
        alerts_high = sum(1 for a in alerts if a.severity == AlertSeverity.HIGH)
        alerts_medium = sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM)
        alerts_low = sum(1 for a in alerts if a.severity == AlertSeverity.LOW)
        
        # Suprimir LOW si hay MEDIUM o HIGH
        if alerts_high > 0 or alerts_medium > 0:
            alerts = [a for a in alerts if a.severity != AlertSeverity.LOW]
            alerts_low = 0
        
        # Log estructurado
        logger.info(
            "password_reset_metrics_calculated "
            "requests=%d emails_sent=%d completed=%d expired=%d "
            "failure_rate=%s avg_time=%s "
            "pending_stock_24h=%d pending_period_24h=%d "
            "tokens_active=%d tokens_expired_stock=%d "
            "alerts_high=%d alerts_medium=%d alerts_low=%d "
            "source=%s partial=%s",
            password_reset_requests, password_reset_emails_sent,
            password_reset_completed, password_reset_expired,
            password_reset_failure_rate, avg_time_to_reset_seconds,
            pending_tokens_stock_24h, pending_created_in_period_24h,
            password_reset_tokens_active, password_reset_tokens_expired_stock,
            alerts_high, alerts_medium, alerts_low,
            email_events_source, email_events_partial,
        )
        
        return PasswordResetOperationalData(
            password_reset_requests=password_reset_requests,
            password_reset_emails_sent=password_reset_emails_sent,
            password_reset_completed=password_reset_completed,
            password_reset_expired=password_reset_expired,
            avg_time_to_reset_seconds=avg_time_to_reset_seconds,
            pending_tokens_stock_24h=pending_tokens_stock_24h,
            pending_created_in_period_24h=pending_created_in_period_24h,
            users_with_multiple_requests=users_with_multiple_requests,
            password_reset_tokens_active=password_reset_tokens_active,
            password_reset_tokens_expired_stock=password_reset_tokens_expired_stock,
            password_reset_failure_rate=password_reset_failure_rate,
            alerts=alerts,
            alerts_high=alerts_high,
            alerts_medium=alerts_medium,
            alerts_low=alerts_low,
            from_date=str(from_d),
            to_date=str(to_d),
            generated_at=now_ts.isoformat(),
            notes=notes,
            thresholds=thresholds,
            email_events_source=email_events_source,
            email_events_partial=email_events_partial,
            resends_instrumented=resends_instrumented,
        )


# Fin del archivo
