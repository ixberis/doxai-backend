# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/operational_deliverability_aggregator.py

Agregador para métricas operativas de entregabilidad de correos de Auth.

Fuentes de datos:
- public.auth_email_events: eventos de email (instrumentado)
  - status: sent | delivered | bounced | complained | failed

Autor: Sistema
Fecha: 2026-01-05
Actualizado: 2026-01-06 - Centralizado AUTH_EMAIL_TYPES desde enums
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

# Import centralized AUTH_EMAIL_TYPES from enums module
from app.modules.auth.enums import AUTH_EMAIL_TYPES

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Umbrales configurables (fuente de verdad)
# Regla de severidad ÚNICA:
#   - Cruza umbral "_high" ⇒ AlertSeverity.HIGH
#   - Cruza umbral "_warn" ⇒ AlertSeverity.MEDIUM
#   - Informativo (ej. >0) ⇒ AlertSeverity.LOW (solo si no hay warn/high)
# ─────────────────────────────────────────────────────────────────
# Umbrales configurables (fuente de verdad)
# Regla de severidad ÚNICA:
#   - Cruza umbral "_high" ⇒ AlertSeverity.HIGH
#   - Cruza umbral "_warn" ⇒ AlertSeverity.MEDIUM
#   - Informativo (ej. >0) ⇒ AlertSeverity.LOW (solo si no hay warn/high)
# ─────────────────────────────────────────────────────────────────

# Tasa de entrega (delivered / sent) - invertida porque valores bajos son malos
DELIVERY_RATE_WARN = 0.90  # <90% → MEDIUM
DELIVERY_RATE_HIGH = 0.80  # <80% → HIGH

# Tasa de rebote (bounced / sent)
BOUNCE_RATE_WARN = 0.05    # ≥5% → MEDIUM
BOUNCE_RATE_HIGH = 0.10    # ≥10% → HIGH

# Tasa de quejas spam (complained / sent)
COMPLAINT_RATE_WARN = 0.001   # ≥0.1% → MEDIUM
COMPLAINT_RATE_HIGH = 0.005   # ≥0.5% → HIGH

# Usuarios con múltiples rebotes
USERS_MULTIPLE_BOUNCES_WARN = 3   # ≥3 usuarios → MEDIUM
USERS_MULTIPLE_BOUNCES_HIGH = 10  # ≥10 usuarios → HIGH


class AlertSeverity(str, Enum):
    """Niveles de severidad para alertas."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class DeliverabilityAlert:
    """Estructura de una alerta de entregabilidad."""
    code: str  # Código estable, ej. HIGH_BOUNCE_RATE
    title: str  # Título humano
    severity: AlertSeverity
    metric: str  # Nombre de la métrica
    value: Union[int, float]  # Conteos = int, ratios = float
    threshold: str  # Umbral como string descriptivo
    time_scope: Literal["periodo", "stock", "tiempo_real"]
    recommended_action: str  # 1-2 líneas para NO técnicos
    details: Optional[str] = None  # Detalles adicionales


@dataclass
class DeliverabilityThresholds:
    """Todos los umbrales usados (para frontend). Fuente de verdad."""
    delivery_rate_warn: float = DELIVERY_RATE_WARN
    delivery_rate_high: float = DELIVERY_RATE_HIGH
    bounce_rate_warn: float = BOUNCE_RATE_WARN
    bounce_rate_high: float = BOUNCE_RATE_HIGH
    complaint_rate_warn: float = COMPLAINT_RATE_WARN
    complaint_rate_high: float = COMPLAINT_RATE_HIGH
    users_multiple_bounces_warn: int = USERS_MULTIPLE_BOUNCES_WARN
    users_multiple_bounces_high: int = USERS_MULTIPLE_BOUNCES_HIGH

    def to_dict(self) -> dict:
        """Convierte a diccionario para serialización."""
        return {
            "delivery_rate_warn": self.delivery_rate_warn,
            "delivery_rate_high": self.delivery_rate_high,
            "bounce_rate_warn": self.bounce_rate_warn,
            "bounce_rate_high": self.bounce_rate_high,
            "complaint_rate_warn": self.complaint_rate_warn,
            "complaint_rate_high": self.complaint_rate_high,
            "users_multiple_bounces_warn": self.users_multiple_bounces_warn,
            "users_multiple_bounces_high": self.users_multiple_bounces_high,
        }


@dataclass
class DeliverabilityOperationalData:
    """Métricas operativas de entregabilidad."""
    
    # Conteos periodo
    emails_sent: int = 0
    emails_delivered: int = 0
    emails_bounced: int = 0
    emails_failed: int = 0
    emails_complained: int = 0
    
    # Tasas (None si no hay datos suficientes o partial instrumentation)
    delivery_rate: Optional[float] = None  # delivered / sent
    bounce_rate: Optional[float] = None    # bounced / sent
    complaint_rate: Optional[float] = None # complained / sent
    
    # Calidad
    users_with_multiple_bounces: int = 0
    
    # Alertas
    alerts: List[DeliverabilityAlert] = field(default_factory=list)
    alerts_high: int = 0
    alerts_medium: int = 0
    alerts_low: int = 0
    
    # Metadata
    from_date: str = ""
    to_date: str = ""
    generated_at: str = ""
    notes: List[str] = field(default_factory=list)
    
    # Umbrales completos (fuente de verdad para frontend)
    thresholds: DeliverabilityThresholds = field(default_factory=DeliverabilityThresholds)
    
    # Trazabilidad
    email_events_source: str = "none"  # instrumented | fallback | none
    email_events_partial: bool = False  # True si solo hay sent/failed sin delivered/bounced/complained


class DeliverabilityOperationalAggregator:
    """
    Agregador para métricas operativas de entregabilidad de correos.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _build_range(self, from_date: date, to_date: date):
        """Construye rango half-open UTC."""
        from_ts = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        return from_ts, to_ts
    
    async def get_deliverability_operational_metrics(
        self,
        from_date: Optional[Union[str, date]] = None,
        to_date: Optional[Union[str, date]] = None,
    ) -> DeliverabilityOperationalData:
        """
        Obtiene métricas operativas de entregabilidad.
        
        Args:
            from_date: Fecha inicio YYYY-MM-DD o date (opcional)
            to_date: Fecha fin YYYY-MM-DD o date (opcional)
        
        Returns:
            DeliverabilityOperationalData con todas las métricas y alertas
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
        
        logger.info(
            "get_deliverability_operational_metrics from=%s to=%s from_ts=%s to_ts=%s",
            from_d, to_d, from_ts, to_ts
        )
        
        notes: List[str] = []
        email_events_source = "none"
        email_events_partial = False
        
        # ─────────────────────────────────────────────────────────────
        # 1. CONTEOS DE EMAILS POR STATUS (periodo) - FILTRADO POR AUTH EMAIL TYPES
        # ─────────────────────────────────────────────────────────────
        emails_sent = 0
        emails_delivered = 0
        emails_bounced = 0
        emails_failed = 0
        emails_complained = 0
        
        has_deliverability_events = False  # True si hay eventos delivered/bounced/complained
        
        try:
            # FIX: asyncpg requiere tuple() (no list()) para ANY() con text().
            # Usamos CAST(:param AS text[]) para bind explícito como array de texto.
            q = text("""
                SELECT 
                    status,
                    COUNT(*) as cnt
                FROM public.auth_email_events
                WHERE created_at >= :from_ts
                  AND created_at < :to_ts
                  AND email_type::text = ANY(CAST(:email_types AS text[]))
                GROUP BY status
            """)
            res = await self.db.execute(q, {
                "from_ts": from_ts, 
                "to_ts": to_ts,
                "email_types": tuple(AUTH_EMAIL_TYPES),
            })
            rows = res.fetchall()
            
            status_counts = {row[0]: int(row[1]) for row in rows}
            
            emails_sent = status_counts.get('sent', 0)
            emails_delivered = status_counts.get('delivered', 0)
            emails_bounced = status_counts.get('bounced', 0)
            emails_failed = status_counts.get('failed', 0)
            emails_complained = status_counts.get('complained', 0)
            
            # Si hay cualquier evento, está instrumentado
            total_events = sum(status_counts.values())
            if total_events > 0:
                email_events_source = "instrumented"
                
                # Verificar si hay eventos de entregabilidad (delivered/bounced/complained)
                deliverability_events = emails_delivered + emails_bounced + emails_complained
                if deliverability_events > 0:
                    has_deliverability_events = True
                else:
                    # Solo hay sent/failed: instrumentación parcial
                    email_events_partial = True
                    notes.append("deliverability: instrumentación parcial (sin eventos de entrega/bounce/complaint)")
                    
        except Exception as e:
            logger.debug("auth_email_events status counts failed: %s", e)
            notes.append("error: no se pudo consultar auth_email_events")
        
        # Si no hay eventos instrumentados, marcar como no instrumentado
        if email_events_source == "none":
            notes.append("deliverability: no instrumentado")
        
        # ─────────────────────────────────────────────────────────────
        # 2. CALCULAR TASAS (SOLO si hay instrumentación completa)
        # ─────────────────────────────────────────────────────────────
        delivery_rate: Optional[float] = None
        bounce_rate: Optional[float] = None
        complaint_rate: Optional[float] = None
        
        # Solo calcular tasas si:
        # - Hay emails enviados
        # - Hay instrumentación completa (no partial)
        # - Hay eventos de entregabilidad
        if emails_sent > 0 and not email_events_partial and has_deliverability_events:
            delivery_rate = round(emails_delivered / emails_sent, 4)
            bounce_rate = round(emails_bounced / emails_sent, 4)
            complaint_rate = round(emails_complained / emails_sent, 4)
        
        # ─────────────────────────────────────────────────────────────
        # 3. USUARIOS CON MÚLTIPLES REBOTES (SOLO SI HAY EVENTOS DE BOUNCE)
        # ─────────────────────────────────────────────────────────────
        users_with_multiple_bounces = 0
        
        if has_deliverability_events:
            try:
                # FIX: asyncpg requiere tuple() (no list()) para ANY() con text().
                q = text("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT user_id
                        FROM public.auth_email_events
                        WHERE status = 'bounced'
                          AND created_at >= :from_ts
                          AND created_at < :to_ts
                          AND email_type::text = ANY(CAST(:email_types AS text[]))
                          AND user_id IS NOT NULL
                        GROUP BY user_id
                        HAVING COUNT(*) > 1
                    ) sub
                """)
                res = await self.db.execute(q, {
                    "from_ts": from_ts, 
                    "to_ts": to_ts,
                    "email_types": tuple(AUTH_EMAIL_TYPES),
                })
                row = res.first()
                if row and row[0]:
                    users_with_multiple_bounces = int(row[0])
            except Exception as e:
                logger.debug("users_with_multiple_bounces failed: %s", e)
        
        # ─────────────────────────────────────────────────────────────
        # 4. GENERAR ALERTAS (SOLO SI HAY INSTRUMENTACIÓN COMPLETA)
        # ─────────────────────────────────────────────────────────────
        alerts: List[DeliverabilityAlert] = []
        
        # Solo generar alertas de tasas si no hay partial instrumentation
        if not email_events_partial:
            alerts = self._generate_alerts(
                emails_sent=emails_sent,
                emails_delivered=emails_delivered,
                emails_bounced=emails_bounced,
                emails_complained=emails_complained,
                delivery_rate=delivery_rate,
                bounce_rate=bounce_rate,
                complaint_rate=complaint_rate,
                users_with_multiple_bounces=users_with_multiple_bounces,
            )
        
        # ─────────────────────────────────────────────────────────────
        # 4.1 SUPRIMIR LOW SI HAY MEDIUM O HIGH (regla única)
        # ─────────────────────────────────────────────────────────────
        has_high_or_medium = any(
            a.severity in (AlertSeverity.HIGH, AlertSeverity.MEDIUM) 
            for a in alerts
        )
        if has_high_or_medium:
            alerts = [a for a in alerts if a.severity != AlertSeverity.LOW]
        
        alerts_high = sum(1 for a in alerts if a.severity == AlertSeverity.HIGH)
        alerts_medium = sum(1 for a in alerts if a.severity == AlertSeverity.MEDIUM)
        alerts_low = sum(1 for a in alerts if a.severity == AlertSeverity.LOW)
        
        # ─────────────────────────────────────────────────────────────
        # 5. LOG ESTRUCTURADO PARA OBSERVABILIDAD
        # ─────────────────────────────────────────────────────────────
        max_severity = "none"
        if alerts_high > 0:
            max_severity = "high"
        elif alerts_medium > 0:
            max_severity = "medium"
        elif alerts_low > 0:
            max_severity = "low"
        
        observability_log = {
            "event_type": "deliverability_operational_metrics_generated",
            "alerts_codes": [a.code for a in alerts],
            "alerts_high": alerts_high,
            "alerts_medium": alerts_medium,
            "alerts_low": alerts_low,
            "max_severity": max_severity,
            "email_events_source": email_events_source,
            "email_events_partial": email_events_partial,
            "sent": emails_sent,
            "failed": emails_failed,
            "delivered": emails_delivered,
            "bounced": emails_bounced,
            "complained": emails_complained,
            "delivery_rate": delivery_rate,
            "bounce_rate": bounce_rate,
            "complaint_rate": complaint_rate,
            "from_date": str(from_d),
            "to_date": str(to_d),
        }
        logger.info("deliverability_operational_metrics_observability: %s", json.dumps(observability_log))
        
        # ─────────────────────────────────────────────────────────────
        # 6. CONSTRUIR RESPUESTA
        # ─────────────────────────────────────────────────────────────
        return DeliverabilityOperationalData(
            emails_sent=emails_sent,
            emails_delivered=emails_delivered,
            emails_bounced=emails_bounced,
            emails_failed=emails_failed,
            emails_complained=emails_complained,
            delivery_rate=delivery_rate,
            bounce_rate=bounce_rate,
            complaint_rate=complaint_rate,
            users_with_multiple_bounces=users_with_multiple_bounces,
            alerts=alerts,
            alerts_high=alerts_high,
            alerts_medium=alerts_medium,
            alerts_low=alerts_low,
            from_date=str(from_d),
            to_date=str(to_d),
            generated_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
            thresholds=DeliverabilityThresholds(),
            email_events_source=email_events_source,
            email_events_partial=email_events_partial,
        )
    
    def _generate_alerts(
        self,
        emails_sent: int,
        emails_delivered: int,
        emails_bounced: int,
        emails_complained: int,
        delivery_rate: Optional[float],
        bounce_rate: Optional[float],
        complaint_rate: Optional[float],
        users_with_multiple_bounces: int,
    ) -> List[DeliverabilityAlert]:
        """Genera alertas según umbrales."""
        alerts: List[DeliverabilityAlert] = []
        
        # ─────────────────────────────────────────────────────────────
        # A) TASA DE ENTREGA (valores bajos son malos - invertido)
        # Solo si tenemos delivery_rate calculado (no None)
        # ─────────────────────────────────────────────────────────────
        if delivery_rate is not None and emails_sent > 0:
            if delivery_rate < DELIVERY_RATE_HIGH:
                alerts.append(DeliverabilityAlert(
                    code="HIGH_DELIVERY_RATE_LOW",
                    title="Tasa de entrega muy baja",
                    severity=AlertSeverity.HIGH,
                    metric="delivery_rate",
                    value=delivery_rate,
                    threshold=f"< {DELIVERY_RATE_HIGH*100:.0f}%",
                    time_scope="periodo",
                    recommended_action="Los correos no están llegando a destino. Verifique que el dominio de envío no esté en listas negras y revise los logs del proveedor de correo.",
                ))
            elif delivery_rate < DELIVERY_RATE_WARN:
                alerts.append(DeliverabilityAlert(
                    code="WARN_DELIVERY_RATE_LOW",
                    title="Tasa de entrega baja",
                    severity=AlertSeverity.MEDIUM,
                    metric="delivery_rate",
                    value=delivery_rate,
                    threshold=f"< {DELIVERY_RATE_WARN*100:.0f}%",
                    time_scope="periodo",
                    recommended_action="La entrega de correos podría estar afectada. Revise si hay problemas con el proveedor de correo o si los correos están cayendo en spam.",
                ))
        
        # ─────────────────────────────────────────────────────────────
        # B) TASA DE REBOTE (valores altos son malos)
        # ─────────────────────────────────────────────────────────────
        if bounce_rate is not None and emails_sent > 0:
            if bounce_rate >= BOUNCE_RATE_HIGH:
                alerts.append(DeliverabilityAlert(
                    code="HIGH_BOUNCE_RATE",
                    title="Demasiados correos rebotados",
                    severity=AlertSeverity.HIGH,
                    metric="bounce_rate",
                    value=bounce_rate,
                    threshold=f"≥ {BOUNCE_RATE_HIGH*100:.0f}%",
                    time_scope="periodo",
                    recommended_action="Muchos correos están siendo rechazados. Esto afecta la reputación del dominio. Revise que las direcciones de email sean válidas y considere limpiar la lista de contactos.",
                ))
            elif bounce_rate >= BOUNCE_RATE_WARN:
                alerts.append(DeliverabilityAlert(
                    code="WARN_BOUNCE_RATE",
                    title="Correos rebotados por encima de lo normal",
                    severity=AlertSeverity.MEDIUM,
                    metric="bounce_rate",
                    value=bounce_rate,
                    threshold=f"≥ {BOUNCE_RATE_WARN*100:.0f}%",
                    time_scope="periodo",
                    recommended_action="Hay rebotes que podrían afectar la reputación. Verifique las direcciones de email de los usuarios que están fallando.",
                ))
            elif emails_bounced > 0:
                alerts.append(DeliverabilityAlert(
                    code="INFO_BOUNCES_DETECTED",
                    title="Se detectaron algunos rebotes",
                    severity=AlertSeverity.LOW,
                    metric="bounce_rate",
                    value=bounce_rate,
                    threshold="> 0",
                    time_scope="periodo",
                    recommended_action="Hay algunos correos rebotados. Esto es normal en pequeñas cantidades, pero conviene monitorear.",
                ))
        
        # ─────────────────────────────────────────────────────────────
        # C) TASA DE QUEJAS SPAM (valores altos son muy malos)
        # ─────────────────────────────────────────────────────────────
        if complaint_rate is not None and emails_sent > 0:
            if complaint_rate >= COMPLAINT_RATE_HIGH:
                alerts.append(DeliverabilityAlert(
                    code="HIGH_SPAM_COMPLAINTS",
                    title="Demasiadas quejas de spam",
                    severity=AlertSeverity.HIGH,
                    metric="complaint_rate",
                    value=complaint_rate,
                    threshold=f"≥ {COMPLAINT_RATE_HIGH*100:.1f}%",
                    time_scope="periodo",
                    recommended_action="Los usuarios están marcando los correos como spam. Esto puede bloquear futuros envíos. Revise el contenido de los correos y asegúrese de que los usuarios esperan recibirlos.",
                ))
            elif complaint_rate >= COMPLAINT_RATE_WARN:
                alerts.append(DeliverabilityAlert(
                    code="WARN_SPAM_COMPLAINTS",
                    title="Quejas de spam detectadas",
                    severity=AlertSeverity.MEDIUM,
                    metric="complaint_rate",
                    value=complaint_rate,
                    threshold=f"≥ {COMPLAINT_RATE_WARN*100:.1f}%",
                    time_scope="periodo",
                    recommended_action="Algunos usuarios marcaron correos como spam. Revise que el contenido sea relevante y que el opt-in sea claro.",
                ))
            elif emails_complained > 0:
                alerts.append(DeliverabilityAlert(
                    code="INFO_SPAM_DETECTED",
                    title="Se detectó alguna queja de spam",
                    severity=AlertSeverity.LOW,
                    metric="complaint_rate",
                    value=complaint_rate,
                    threshold="> 0",
                    time_scope="periodo",
                    recommended_action="Hubo alguna queja de spam. Conviene revisar el contenido de los correos.",
                ))
        
        # ─────────────────────────────────────────────────────────────
        # D) USUARIOS CON MÚLTIPLES REBOTES
        # ─────────────────────────────────────────────────────────────
        if users_with_multiple_bounces >= USERS_MULTIPLE_BOUNCES_HIGH:
            alerts.append(DeliverabilityAlert(
                code="HIGH_USERS_MULTIPLE_BOUNCES",
                title="Muchos usuarios con rebotes repetidos",
                severity=AlertSeverity.HIGH,
                metric="users_with_multiple_bounces",
                value=users_with_multiple_bounces,
                threshold=f"≥ {USERS_MULTIPLE_BOUNCES_HIGH} usuarios",
                time_scope="periodo",
                recommended_action="Hay usuarios cuyos correos rebotan repetidamente. Considere desactivar el envío a estas direcciones o contactarlos por otro medio.",
            ))
        elif users_with_multiple_bounces >= USERS_MULTIPLE_BOUNCES_WARN:
            alerts.append(DeliverabilityAlert(
                code="WARN_USERS_MULTIPLE_BOUNCES",
                title="Algunos usuarios con rebotes repetidos",
                severity=AlertSeverity.MEDIUM,
                metric="users_with_multiple_bounces",
                value=users_with_multiple_bounces,
                threshold=f"≥ {USERS_MULTIPLE_BOUNCES_WARN} usuarios",
                time_scope="periodo",
                recommended_action="Hay usuarios con múltiples rebotes. Revise si las direcciones de email son correctas.",
            ))
        elif users_with_multiple_bounces > 0:
            alerts.append(DeliverabilityAlert(
                code="INFO_USERS_MULTIPLE_BOUNCES",
                title="Usuario(s) con rebotes repetidos",
                severity=AlertSeverity.LOW,
                metric="users_with_multiple_bounces",
                value=users_with_multiple_bounces,
                threshold="> 0",
                time_scope="periodo",
                recommended_action="Algunos usuarios tienen más de un rebote. Esto es normal en pequeñas cantidades.",
            ))
        
        return alerts


# Fin del archivo
