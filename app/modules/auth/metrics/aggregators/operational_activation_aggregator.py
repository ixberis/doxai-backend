# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/operational_activation_aggregator.py

Agregador para métricas operativas de activación de Auth.

Fuentes de datos:
- public.account_activations: tokens de activación, estados
- public.auth_email_events: emails enviados (instrumentado)
- public.app_users: usuarios y estados de activación

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

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Umbrales configurables (fuente de verdad)
# Regla de severidad ÚNICA:
#   - Cruza umbral "_high" ⇒ AlertSeverity.HIGH
#   - Cruza umbral "_warn" ⇒ AlertSeverity.MEDIUM
#   - Informativo (ej. >0) ⇒ AlertSeverity.LOW (solo si no hay warn/high)
# ─────────────────────────────────────────────────────────────────

# Tokens expirados sin activar
ACTIVATION_EXPIRATIONS_WARN = 3  # ≥3 → MEDIUM
ACTIVATION_EXPIRATIONS_HIGH = 10  # ≥10 → HIGH

# Tasa de fallo de activación (1 - completed/sent)
ACTIVATION_FAILURE_RATE_WARN = 0.30  # 30% fallos → MEDIUM  
ACTIVATION_FAILURE_RATE_HIGH = 0.50  # 50% fallos → HIGH

# Tiempo promedio de activación (segundos)
# Más de 24h promedio es preocupante
SLOW_ACTIVATION_WARN = 86400  # 24h → MEDIUM
SLOW_ACTIVATION_HIGH = 172800  # 48h → HIGH

# Múltiples reenvíos por usuario
MULTIPLE_RESENDS_WARN = 3  # ≥3 → MEDIUM
MULTIPLE_RESENDS_HIGH = 10  # ≥10 → HIGH

# Pendientes de activación (>24h sin activar) - ALINEADO con regla única
PENDING_ACTIVATIONS_WARN = 5  # ≥5 → MEDIUM (no LOW)
PENDING_ACTIVATIONS_HIGH = 20  # ≥20 → HIGH


class AlertSeverity(str, Enum):
    """Niveles de severidad para alertas."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ActivationAlert:
    """Estructura de una alerta de activación."""
    code: str  # Código estable, ej. HIGH_ACTIVATION_EXPIRATIONS
    title: str  # Título humano
    severity: AlertSeverity
    metric: str  # Nombre de la métrica
    value: Union[int, float]  # Conteos = int, ratios = float
    threshold: str  # Umbral como string descriptivo
    time_scope: Literal["periodo", "stock", "tiempo_real"]
    recommended_action: str  # 1-2 líneas para NO técnicos
    details: Optional[str] = None  # Detalles adicionales


@dataclass
class ActivationThresholds:
    """Todos los umbrales usados (para frontend). Fuente de verdad."""
    activation_expirations_warn: int = ACTIVATION_EXPIRATIONS_WARN
    activation_expirations_high: int = ACTIVATION_EXPIRATIONS_HIGH
    activation_failure_rate_warn: float = ACTIVATION_FAILURE_RATE_WARN
    activation_failure_rate_high: float = ACTIVATION_FAILURE_RATE_HIGH
    slow_activation_warn: int = SLOW_ACTIVATION_WARN
    slow_activation_high: int = SLOW_ACTIVATION_HIGH
    multiple_resends_warn: int = MULTIPLE_RESENDS_WARN
    multiple_resends_high: int = MULTIPLE_RESENDS_HIGH
    pending_activations_warn: int = PENDING_ACTIVATIONS_WARN
    pending_activations_high: int = PENDING_ACTIVATIONS_HIGH

    def to_dict(self) -> dict:
        """Convierte a diccionario para serialización."""
        return {
            "activation_expirations_warn": self.activation_expirations_warn,
            "activation_expirations_high": self.activation_expirations_high,
            "activation_failure_rate_warn": self.activation_failure_rate_warn,
            "activation_failure_rate_high": self.activation_failure_rate_high,
            "slow_activation_warn": self.slow_activation_warn,
            "slow_activation_high": self.slow_activation_high,
            "multiple_resends_warn": self.multiple_resends_warn,
            "multiple_resends_high": self.multiple_resends_high,
            "pending_activations_warn": self.pending_activations_warn,
            "pending_activations_high": self.pending_activations_high,
        }


@dataclass
class ActivationOperationalData:
    """Métricas operativas de activación."""
    
    # Periodo
    activation_emails_sent: int = 0
    activations_completed: int = 0
    activation_tokens_expired: int = 0
    activation_resends: int = 0
    avg_time_to_activate_seconds: Optional[float] = None
    
    # Calidad / Pendientes
    pending_tokens_stock_24h: int = 0  # Stock: tokens vigentes, creados hace >24h, sin consumir
    pending_created_in_period_24h: int = 0  # Periodo: creados en [from,to) que ya pasaron 24h sin activar
    users_with_multiple_resends: int = 0  # Usuarios con >1 reenvío
    
    # Stock (estado actual)
    activation_tokens_active: int = 0  # Tokens válidos ahora
    activation_tokens_expired_stock: int = 0  # Tokens expirados (stock)
    
    # Tasa de fallo
    activation_failure_rate: Optional[float] = None  # 1 - (completed/sent)
    
    # Alertas
    alerts: List[ActivationAlert] = field(default_factory=list)
    alerts_high: int = 0
    alerts_medium: int = 0
    alerts_low: int = 0
    
    # Metadata
    from_date: str = ""
    to_date: str = ""
    generated_at: str = ""
    notes: List[str] = field(default_factory=list)
    
    # Umbrales completos (fuente de verdad para frontend)
    thresholds: ActivationThresholds = field(default_factory=ActivationThresholds)
    
    # Trazabilidad
    email_events_source: str = "none"  # instrumented | fallback | none
    email_events_partial: bool = False  # True si source=='fallback'
    resends_instrumented: bool = False

    # Deprecado pero mantenido para compatibilidad UI
    @property
    def activations_not_completed_24h(self) -> int:
        """Alias para compatibilidad con UI. Devuelve pending_tokens_stock_24h."""
        return self.pending_tokens_stock_24h


class ActivationOperationalAggregator:
    """
    Agregador para métricas operativas de activación.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _build_range(self, from_date: date, to_date: date):
        """Construye rango half-open UTC."""
        from_ts = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        return from_ts, to_ts
    
    async def get_activation_operational_metrics(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> ActivationOperationalData:
        """
        Obtiene métricas operativas de activación.
        
        Args:
            from_date: Fecha inicio YYYY-MM-DD (opcional)
            to_date: Fecha fin YYYY-MM-DD (opcional)
        
        Returns:
            ActivationOperationalData con todas las métricas y alertas
        """
        # Default: últimos 7 días
        if not from_date or not to_date:
            today = datetime.now(timezone.utc).date()
            from_d = today - timedelta(days=7)
            to_d = today
        else:
            from_d = datetime.strptime(from_date, "%Y-%m-%d").date()
            to_d = datetime.strptime(to_date, "%Y-%m-%d").date()
        
        from_ts, to_ts = self._build_range(from_d, to_d)
        now_ts = datetime.now(timezone.utc)
        threshold_24h = now_ts - timedelta(hours=24)
        
        logger.info(
            "get_activation_operational_metrics from=%s to=%s from_ts=%s to_ts=%s",
            from_d, to_d, from_ts, to_ts
        )
        
        notes: List[str] = []
        email_events_source = "none"
        email_events_partial = False
        resends_instrumented = False
        
        # ─────────────────────────────────────────────────────────────
        # 1. EMAILS ENVIADOS (periodo) - Preferir auth_email_events
        # ─────────────────────────────────────────────────────────────
        activation_emails_sent = 0
        instrumented_count = 0
        
        # Intentar fuente instrumentada primero
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.auth_email_events
                WHERE email_type = 'account_activation'
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
            activation_emails_sent = instrumented_count
            email_events_source = "instrumented"
        else:
            # Fallback a account_activations.activation_email_sent_at
            try:
                q = text("""
                    SELECT COUNT(*)
                    FROM public.account_activations
                    WHERE activation_email_sent_at >= :from_ts
                      AND activation_email_sent_at < :to_ts
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0]:
                    activation_emails_sent = int(row[0])
                    email_events_source = "fallback"
                    email_events_partial = True
            except Exception as e:
                logger.debug("fallback email count failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 2. ACTIVACIONES COMPLETADAS (periodo)
        # ─────────────────────────────────────────────────────────────
        activations_completed = 0
        
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.account_activations
                WHERE consumed_at IS NOT NULL
                  AND consumed_at >= :from_ts
                  AND consumed_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                activations_completed = int(row[0])
        except Exception as e:
            logger.debug("activations_completed failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 3. TOKENS EXPIRADOS (periodo)
        # NO usar status='expired'. Usar: expires_at en rango Y consumed_at IS NULL Y expires_at < NOW()
        # ─────────────────────────────────────────────────────────────
        activation_tokens_expired = 0
        
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.account_activations
                WHERE consumed_at IS NULL
                  AND expires_at >= :from_ts
                  AND expires_at < :to_ts
                  AND expires_at < :now_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts, "now_ts": now_ts})
            row = res.first()
            if row and row[0]:
                activation_tokens_expired = int(row[0])
        except Exception as e:
            logger.debug("activation_tokens_expired failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 4. REENVÍOS (periodo) - SQL corregido con SUM(GREATEST(cnt-1, 0))
        # ─────────────────────────────────────────────────────────────
        activation_resends = 0
        users_with_multiple_resends = 0
        
        try:
            q = text("""
                SELECT
                    COALESCE(SUM(GREATEST(cnt - 1, 0)), 0) AS resends,
                    COALESCE(COUNT(*) FILTER (WHERE cnt > 1), 0) AS users_multiple
                FROM (
                    SELECT user_id, COUNT(*) AS cnt
                    FROM public.auth_email_events
                    WHERE email_type = 'account_activation'
                      AND status = 'sent'
                      AND created_at >= :from_ts
                      AND created_at < :to_ts
                      AND user_id IS NOT NULL
                    GROUP BY user_id
                ) sub
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row:
                activation_resends = int(row[0] or 0)
                users_with_multiple_resends = int(row[1] or 0)
                # Solo marcamos instrumentado si hay eventos sent en el periodo
                resends_instrumented = True
        except Exception as e:
            logger.debug("resends from auth_email_events failed: %s", e)
            notes.append("resends: no instrumentado")
        
        # Verificar si realmente hay eventos para marcar resends_instrumented
        if resends_instrumented:
            try:
                q = text("""
                    SELECT COUNT(*) FROM public.auth_email_events
                    WHERE email_type = 'account_activation'
                      AND status = 'sent'
                      AND created_at >= :from_ts
                      AND created_at < :to_ts
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if not row or row[0] == 0:
                    resends_instrumented = False
            except Exception:
                resends_instrumented = False
        
        # ─────────────────────────────────────────────────────────────
        # 5. TIEMPO PROMEDIO DE ACTIVACIÓN (periodo)
        # ─────────────────────────────────────────────────────────────
        avg_time_to_activate_seconds: Optional[float] = None
        
        try:
            q = text("""
                SELECT AVG(EXTRACT(EPOCH FROM (consumed_at - created_at)))
                FROM public.account_activations
                WHERE consumed_at IS NOT NULL
                  AND consumed_at >= :from_ts
                  AND consumed_at < :to_ts
                  AND consumed_at > created_at
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                avg_time_to_activate_seconds = round(float(row[0]), 2)
        except Exception as e:
            logger.debug("avg_time_to_activate failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 6. PENDIENTES >24H - Separar STOCK vs PERIODO
        # ─────────────────────────────────────────────────────────────
        pending_tokens_stock_24h = 0
        pending_created_in_period_24h = 0
        
        # Stock: tokens vigentes (expires_at > now), creados hace >24h, sin consumir
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.account_activations
                WHERE consumed_at IS NULL
                  AND expires_at > :now_ts
                  AND created_at < :threshold_24h
            """)
            res = await self.db.execute(q, {"now_ts": now_ts, "threshold_24h": threshold_24h})
            row = res.first()
            if row and row[0]:
                pending_tokens_stock_24h = int(row[0])
        except Exception as e:
            logger.debug("pending_tokens_stock_24h failed: %s", e)
        
        # Periodo: creados en [from_ts, to_ts), que ya pasaron 24h sin activar, y siguen vigentes
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.account_activations
                WHERE consumed_at IS NULL
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
        # 7. STOCK: Tokens activos y expirados (sin usar status enum)
        # ─────────────────────────────────────────────────────────────
        activation_tokens_active = 0
        activation_tokens_expired_stock = 0
        
        # Tokens válidos ahora: consumed_at IS NULL y expires_at > NOW()
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.account_activations
                WHERE consumed_at IS NULL
                  AND expires_at > :now_ts
            """)
            res = await self.db.execute(q, {"now_ts": now_ts})
            row = res.first()
            if row and row[0]:
                activation_tokens_active = int(row[0])
        except Exception as e:
            logger.debug("activation_tokens_active failed: %s", e)
        
        # Tokens expirados (stock histórico): consumed_at IS NULL y expires_at < NOW()
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.account_activations
                WHERE consumed_at IS NULL
                  AND expires_at < :now_ts
            """)
            res = await self.db.execute(q, {"now_ts": now_ts})
            row = res.first()
            if row and row[0]:
                activation_tokens_expired_stock = int(row[0])
        except Exception as e:
            logger.debug("activation_tokens_expired_stock failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # CALCULAR TASA DE FALLO
        # ─────────────────────────────────────────────────────────────
        activation_failure_rate: Optional[float] = None
        failure_rate_inconsistent = False
        
        if activation_emails_sent > 0:
            if activations_completed > activation_emails_sent:
                # Caso inconsistente: completados > enviados (puede pasar por rangos)
                failure_rate_inconsistent = True
                notes.append("failure_rate: inconsistente (completados > enviados en rango)")
                # No calculamos failure rate para evitar alertas falsas
            else:
                completion_rate = activations_completed / activation_emails_sent
                activation_failure_rate = round(1 - completion_rate, 4)
        
        generated_at = datetime.now(timezone.utc).isoformat()
        
        # ─────────────────────────────────────────────────────────────
        # CONSTRUIR ALERTAS
        # ─────────────────────────────────────────────────────────────
        alerts: List[ActivationAlert] = []
        thresholds = ActivationThresholds()
        
        # 1. Tokens expirados (periodo)
        if activation_tokens_expired >= thresholds.activation_expirations_high:
            alerts.append(ActivationAlert(
                code="HIGH_ACTIVATION_EXPIRATIONS",
                title="Muchos usuarios no activaron su cuenta",
                severity=AlertSeverity.HIGH,
                metric="activation_tokens_expired",
                value=activation_tokens_expired,
                threshold=f"≥{thresholds.activation_expirations_high}",
                time_scope="periodo",
                recommended_action="Revisar si los correos de activación están llegando. Verificar carpeta de spam o problemas de entrega.",
            ))
        elif activation_tokens_expired >= thresholds.activation_expirations_warn:
            alerts.append(ActivationAlert(
                code="WARN_ACTIVATION_EXPIRATIONS",
                title="Algunos usuarios no activaron su cuenta",
                severity=AlertSeverity.MEDIUM,
                metric="activation_tokens_expired",
                value=activation_tokens_expired,
                threshold=f"≥{thresholds.activation_expirations_warn}",
                time_scope="periodo",
                recommended_action="Monitorear tendencia. Puede indicar problemas con el correo de activación.",
            ))
        
        # 2. Tasa de fallo alta (solo si no es inconsistente)
        if activation_failure_rate is not None and not failure_rate_inconsistent:
            if activation_failure_rate >= thresholds.activation_failure_rate_high:
                alerts.append(ActivationAlert(
                    code="HIGH_ACTIVATION_FAILURE_RATE",
                    title="Muy pocos usuarios completan la activación",
                    severity=AlertSeverity.HIGH,
                    metric="activation_failure_rate",
                    value=activation_failure_rate,
                    threshold=f"≥{int(thresholds.activation_failure_rate_high * 100)}%",
                    time_scope="periodo",
                    recommended_action="Urgente: revisar proceso de activación. El correo puede no estar llegando o el enlace es confuso.",
                ))
            elif activation_failure_rate >= thresholds.activation_failure_rate_warn:
                alerts.append(ActivationAlert(
                    code="WARN_ACTIVATION_FAILURE_RATE",
                    title="Tasa de activación baja",
                    severity=AlertSeverity.MEDIUM,
                    metric="activation_failure_rate",
                    value=activation_failure_rate,
                    threshold=f"≥{int(thresholds.activation_failure_rate_warn * 100)}%",
                    time_scope="periodo",
                    recommended_action="Revisar el mensaje de activación y la experiencia del usuario.",
                ))
        
        # 3. Tiempo promedio alto
        if avg_time_to_activate_seconds is not None:
            if avg_time_to_activate_seconds >= thresholds.slow_activation_high:
                alerts.append(ActivationAlert(
                    code="HIGH_SLOW_ACTIVATIONS",
                    title="Los usuarios tardan mucho en activar",
                    severity=AlertSeverity.HIGH,
                    metric="avg_time_to_activate_seconds",
                    value=avg_time_to_activate_seconds,
                    threshold=f"≥{thresholds.slow_activation_high // 3600}h",
                    time_scope="periodo",
                    recommended_action="Urgente: el correo puede estar llegando tarde o el proceso es confuso.",
                ))
            elif avg_time_to_activate_seconds >= thresholds.slow_activation_warn:
                alerts.append(ActivationAlert(
                    code="WARN_SLOW_ACTIVATIONS",
                    title="Tiempo de activación elevado",
                    severity=AlertSeverity.MEDIUM,
                    metric="avg_time_to_activate_seconds",
                    value=avg_time_to_activate_seconds,
                    threshold=f"≥{thresholds.slow_activation_warn // 3600}h",
                    time_scope="periodo",
                    recommended_action="Considerar hacer el proceso más claro o enviar recordatorios.",
                ))
        
        # 4. Múltiples reenvíos
        if users_with_multiple_resends >= thresholds.multiple_resends_high:
            alerts.append(ActivationAlert(
                code="HIGH_MULTIPLE_RESENDS",
                title="Muchos usuarios necesitan reenvíos",
                severity=AlertSeverity.HIGH,
                metric="users_with_multiple_resends",
                value=users_with_multiple_resends,
                threshold=f"≥{thresholds.multiple_resends_high}",
                time_scope="periodo",
                recommended_action="El correo no está llegando. Revisar configuración de email y spam.",
            ))
        elif users_with_multiple_resends >= thresholds.multiple_resends_warn:
            alerts.append(ActivationAlert(
                code="WARN_MULTIPLE_RESENDS",
                title="Usuarios solicitando reenvíos",
                severity=AlertSeverity.MEDIUM,
                metric="users_with_multiple_resends",
                value=users_with_multiple_resends,
                threshold=f"≥{thresholds.multiple_resends_warn}",
                time_scope="periodo",
                recommended_action="Verificar que los correos llegan correctamente.",
            ))
        
        # 5. Pendientes de activación (stock) - REGLA ÚNICA ALINEADA
        # >= HIGH → HIGH, >= WARN → MEDIUM
        if pending_tokens_stock_24h >= thresholds.pending_activations_high:
            alerts.append(ActivationAlert(
                code="HIGH_PENDING_ACTIVATIONS",
                title="Muchos usuarios pendientes de activar",
                severity=AlertSeverity.HIGH,
                metric="pending_tokens_stock_24h",
                value=pending_tokens_stock_24h,
                threshold=f"≥{thresholds.pending_activations_high}",
                time_scope="stock",
                recommended_action="Urgente: hay muchos usuarios esperando activar. Verificar entrega de correos.",
            ))
        elif pending_tokens_stock_24h >= thresholds.pending_activations_warn:
            alerts.append(ActivationAlert(
                code="WARN_PENDING_ACTIVATIONS",
                title="Usuarios pendientes de activar",
                severity=AlertSeverity.MEDIUM,
                metric="pending_tokens_stock_24h",
                value=pending_tokens_stock_24h,
                threshold=f"≥{thresholds.pending_activations_warn}",
                time_scope="stock",
                recommended_action="Hay usuarios esperando activar. Considerar enviar recordatorio.",
            ))
        
        # Contar por severidad
        alerts_high = sum(1 for a in alerts if a.severity == AlertSeverity.HIGH)
        alerts_medium = sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM)
        alerts_low = sum(1 for a in alerts if a.severity == AlertSeverity.LOW)
        
        # ─────────────────────────────────────────────────────────────
        # LOG ESTRUCTURADO PARA OBSERVABILIDAD FUTURA
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
            "event_type": "activation_operational_metrics_generated",
            "from_date": from_d.isoformat(),
            "to_date": to_d.isoformat(),
            "alerts_high": alerts_high,
            "alerts_medium": alerts_medium,
            "alerts_low": alerts_low,
            "alerts_codes": alerts_codes,
            "max_severity": max_severity,
            "emails_sent": activation_emails_sent,
            "completed": activations_completed,
            "expired": activation_tokens_expired,
            "failure_rate": activation_failure_rate,
            "email_source": email_events_source,
            "pending_stock_24h": pending_tokens_stock_24h,
            "pending_period_24h": pending_created_in_period_24h,
        }
        
        logger.info(
            "activation_operational_metrics %s",
            json.dumps(observability_log, ensure_ascii=False)
        )
        
        return ActivationOperationalData(
            activation_emails_sent=activation_emails_sent,
            activations_completed=activations_completed,
            activation_tokens_expired=activation_tokens_expired,
            activation_resends=activation_resends,
            avg_time_to_activate_seconds=avg_time_to_activate_seconds,
            pending_tokens_stock_24h=pending_tokens_stock_24h,
            pending_created_in_period_24h=pending_created_in_period_24h,
            users_with_multiple_resends=users_with_multiple_resends,
            activation_tokens_active=activation_tokens_active,
            activation_tokens_expired_stock=activation_tokens_expired_stock,
            activation_failure_rate=activation_failure_rate,
            alerts=alerts,
            alerts_high=alerts_high,
            alerts_medium=alerts_medium,
            alerts_low=alerts_low,
            from_date=from_d.isoformat(),
            to_date=to_d.isoformat(),
            generated_at=generated_at,
            notes=notes,
            thresholds=thresholds,
            email_events_source=email_events_source,
            email_events_partial=email_events_partial,
            resends_instrumented=resends_instrumented,
        )


# Fin del archivo
