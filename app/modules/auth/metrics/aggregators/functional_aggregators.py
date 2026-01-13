# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/functional_aggregators.py

Agregadores para métricas de Auth Funcional con rango de fechas.
Cubre: Activation, Password Reset, Users (paginados).

Autor: Sistema
Fecha: 2026-01-04
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, time, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ActivationMetrics:
    """Métricas de activación por rango."""
    activation_emails_sent: int
    activations_completed: int
    resends: int
    tokens_expired: int
    completion_rate: Optional[float]
    avg_time_to_activate_seconds: Optional[float]
    sample_count: int
    from_date: str
    to_date: str
    generated_at: str
    # Flags de trazabilidad
    email_events_source: str  # "instrumented" | "fallback" | "none"
    email_events_partial: bool  # True si se usó fallback


@dataclass
class PasswordResetMetrics:
    """Métricas de password reset por rango."""
    requests_total: int
    completed_total: int
    tokens_expired: int
    abandon_rate: Optional[float]
    completion_rate: Optional[float]
    avg_time_seconds: Optional[float]
    sample_count: int
    from_date: str
    to_date: str
    generated_at: str


@dataclass
class UsersAnalyticsMetrics:
    """Métricas analíticas de usuarios (sin lista individual)."""
    # Periodo
    created_in_period: int
    activated_in_period: int
    deleted_in_period: int
    # Stock (estado actual)
    activated_stock: int
    active_stock: int
    suspended_stock: int
    deleted_stock: int
    # Calidad de activación
    not_activated_24h: int  # Usuarios creados que no activaron tras 24h
    activation_time_p95_hours: Optional[float]  # Percentil 95 tiempo a activar
    activation_retries: int  # Usuarios que recibieron >1 email de activación
    activation_retries_instrumented: bool  # True si activation_retries viene de auth_email_events
    # Conversión
    activation_rate: Optional[float]  # activados / creados en periodo
    activated_no_session: int  # Usuarios activados sin ninguna sesión (stock)
    activated_no_session_in_period: int  # Activados en periodo sin sesión aún
    # Estados críticos
    suspended_created_in_period: int  # Suspendidos creados en periodo
    deleted_not_activated: int  # Eliminados sin activar (stock/histórico)
    deleted_not_activated_in_period: int  # Eliminados en periodo sin activar
    # Metadata
    from_date: str
    to_date: str
    generated_at: str


class FunctionalAggregators:
    """
    Agregadores para secciones de Auth Funcional con soporte de rango.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _build_range(self, from_date: date, to_date: date):
        """Construye rango half-open UTC."""
        from_ts = datetime.combine(from_date, time.min, tzinfo=timezone.utc)
        to_ts = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        return from_ts, to_ts
    
    @staticmethod
    def _mask_email(email: str) -> str:
        """Enmascara email: us***@dom***.com"""
        if not email or '@' not in email:
            return '***@***.***'
        local, domain = email.rsplit('@', 1)
        local_masked = local[:2] + '***' if len(local) > 2 else '***'
        domain_parts = domain.rsplit('.', 1)
        if len(domain_parts) == 2:
            domain_masked = domain_parts[0][:3] + '***.' + domain_parts[1]
        else:
            domain_masked = '***'
        return f"{local_masked}@{domain_masked}"
    
    # ─────────────────────────────────────────────────────────────
    # Activation Metrics
    # ─────────────────────────────────────────────────────────────
    
    async def get_activation_metrics(self, from_date: date, to_date: date) -> ActivationMetrics:
        """
        Obtiene métricas de activación para un rango de fechas.
        
        Fuentes:
        - Primaria: public.auth_email_events (emails enviados de tipo activation)
        - Fallback: public.account_activations.activation_email_sent_at (si no hay eventos)
        - public.account_activations (activaciones, reenvíos, expirados)
        
        El campo email_events_source indica la fuente usada:
        - "instrumented": datos de auth_email_events
        - "fallback": datos estimados de account_activations.activation_email_sent_at
        - "none": no se encontraron datos
        """
        from_ts, to_ts = self._build_range(from_date, to_date)
        
        logger.info(
            "get_activation_metrics from=%s to=%s from_ts=%s to_ts=%s",
            from_date, to_date, from_ts, to_ts
        )
        
        activation_emails_sent = 0
        activations_completed = 0
        resends = 0
        tokens_expired = 0
        avg_time_seconds = None
        sample_count = 0
        email_events_source = "none"
        email_events_partial = False
        
        # 1. Emails de activación enviados en el periodo
        # Fuente primaria: auth_email_events (instrumentación)
        emails_from_events = 0
        emails_from_fallback = 0
        
        try:
            q = text("""
                SELECT COUNT(*) 
                FROM public.auth_email_events
                WHERE email_type = 'activation'
                  AND status = 'sent'
                  AND created_at >= :from_ts
                  AND created_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                emails_from_events = int(row[0])
        except Exception as e:
            logger.debug("activation_emails_sent from events failed: %s", e)
        
        # Fuente fallback: account_activations.activation_email_sent_at
        try:
            q_fallback = text("""
                SELECT COUNT(*)
                FROM public.account_activations
                WHERE activation_email_sent_at >= :from_ts
                  AND activation_email_sent_at < :to_ts
            """)
            res = await self.db.execute(q_fallback, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                emails_from_fallback = int(row[0])
        except Exception as e:
            logger.debug("activation_emails_sent from fallback failed: %s", e)
        
        # Decisión de fuente: usar eventos si existen, sino fallback
        if emails_from_events > 0:
            activation_emails_sent = emails_from_events
            email_events_source = "instrumented"
            email_events_partial = False
            logger.debug("activation_emails: using instrumented source (%d)", emails_from_events)
        elif emails_from_fallback > 0:
            activation_emails_sent = emails_from_fallback
            email_events_source = "fallback"
            email_events_partial = True
            logger.info("activation_emails: using fallback source (%d) - events not instrumented", emails_from_fallback)
        else:
            email_events_source = "none"
            email_events_partial = False
        
        # 2. Activaciones completadas en el periodo (account_activations uses consumed_at)
        try:
            q = text("""
                SELECT COUNT(DISTINCT user_id)
                FROM public.account_activations
                WHERE status = 'used'
                  AND consumed_at >= :from_ts
                  AND consumed_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                activations_completed = int(row[0])
            logger.debug("activation_consumed_col=consumed_at")
        except Exception as e:
            logger.warning("activations_completed failed: %s", e)
        
        # 3. Reenvíos (emails enviados > 1 por usuario en el periodo)
        # Solo disponible si tenemos datos de auth_email_events
        if email_events_source == "instrumented":
            try:
                q = text("""
                    SELECT COALESCE(SUM(cnt - 1), 0)
                    FROM (
                        SELECT user_id, COUNT(*) as cnt
                        FROM public.auth_email_events
                        WHERE email_type = 'activation'
                          AND status = 'sent'
                          AND created_at >= :from_ts
                          AND created_at < :to_ts
                        GROUP BY user_id
                        HAVING COUNT(*) > 1
                    ) sub
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0]:
                    resends = int(row[0])
            except Exception as e:
                logger.debug("resends count failed: %s", e)
        
        # 4. Tokens expirados sin usar en el periodo
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.account_activations
                WHERE status != 'used'
                  AND consumed_at IS NULL
                  AND expires_at < NOW()
                  AND expires_at >= :from_ts
                  AND expires_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                tokens_expired = int(row[0])
        except Exception as e:
            logger.warning("tokens_expired failed: %s", e)
        
        # 5. Tiempo promedio de activación (segundos)
        try:
            q = text("""
                SELECT 
                    AVG(EXTRACT(EPOCH FROM (consumed_at - created_at))) as avg_seconds,
                    COUNT(*) as sample_count
                FROM public.account_activations
                WHERE status = 'used'
                  AND consumed_at >= :from_ts
                  AND consumed_at < :to_ts
                  AND consumed_at > created_at
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row:
                if row.avg_seconds:
                    avg_time_seconds = round(float(row.avg_seconds), 2)
                sample_count = int(row.sample_count or 0)
        except Exception as e:
            logger.warning("avg_time_to_activate failed: %s", e)
        
        # Calcular tasa de completado
        completion_rate = None
        if activation_emails_sent > 0:
            completion_rate = round(activations_completed / activation_emails_sent, 4)
        
        generated_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(
            "get_activation_metrics completed: emails=%d (source=%s, partial=%s) completed=%d resends=%d expired=%d rate=%s avg=%s",
            activation_emails_sent, email_events_source, email_events_partial,
            activations_completed, resends, tokens_expired,
            completion_rate, avg_time_seconds
        )
        
        return ActivationMetrics(
            activation_emails_sent=activation_emails_sent,
            activations_completed=activations_completed,
            resends=resends,
            tokens_expired=tokens_expired,
            completion_rate=completion_rate,
            avg_time_to_activate_seconds=avg_time_seconds,
            sample_count=sample_count,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            generated_at=generated_at,
            email_events_source=email_events_source,
            email_events_partial=email_events_partial,
        )
    
    # ─────────────────────────────────────────────────────────────
    # Password Reset Metrics
    # ─────────────────────────────────────────────────────────────
    
    async def get_password_reset_metrics(self, from_date: date, to_date: date) -> PasswordResetMetrics:
        """
        Obtiene métricas de password reset para un rango de fechas.
        
        Fuente: public.password_resets
        """
        from_ts, to_ts = self._build_range(from_date, to_date)
        
        logger.info(
            "get_password_reset_metrics from=%s to=%s",
            from_date, to_date
        )
        
        requests_total = 0
        completed_total = 0
        tokens_expired = 0
        avg_time_seconds = None
        sample_count = 0
        
        # 1. Solicitudes de reset en el periodo
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
                requests_total = int(row[0])
        except Exception as e:
            logger.warning("password_reset requests_total failed: %s", e)
        
        # 2. Resets completados en el periodo (password_resets uses used_at, not consumed_at)
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
                completed_total = int(row[0])
            logger.debug("password_reset_consumed_col=used_at")
        except Exception as e:
            logger.warning("password_reset completed_total failed: %s", e)
        
        # 3. Tokens expirados sin usar (password_resets uses used_at)
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.password_resets
                WHERE used_at IS NULL
                  AND expires_at < NOW()
                  AND expires_at >= :from_ts
                  AND expires_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                tokens_expired = int(row[0])
        except Exception as e:
            logger.warning("password_reset tokens_expired failed: %s", e)
        
        # 4. Tiempo promedio de completar reset (uses used_at)
        try:
            q = text("""
                SELECT 
                    AVG(EXTRACT(EPOCH FROM (used_at - created_at))) as avg_seconds,
                    COUNT(*) as sample_count
                FROM public.password_resets
                WHERE used_at IS NOT NULL
                  AND used_at >= :from_ts
                  AND used_at < :to_ts
                  AND used_at > created_at
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row:
                if row.avg_seconds:
                    avg_time_seconds = round(float(row.avg_seconds), 2)
                sample_count = int(row.sample_count or 0)
        except Exception as e:
            logger.warning("password_reset avg_time failed: %s", e)
        
        # Calcular tasas
        completion_rate = None
        abandon_rate = None
        if requests_total > 0:
            completion_rate = round(completed_total / requests_total, 4)
            abandon_rate = round((requests_total - completed_total) / requests_total, 4)
        
        generated_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(
            "get_password_reset_metrics completed: requests=%d completed=%d expired=%d rate=%s",
            requests_total, completed_total, tokens_expired, completion_rate
        )
        
        return PasswordResetMetrics(
            requests_total=requests_total,
            completed_total=completed_total,
            tokens_expired=tokens_expired,
            abandon_rate=abandon_rate,
            completion_rate=completion_rate,
            avg_time_seconds=avg_time_seconds,
            sample_count=sample_count,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            generated_at=generated_at,
        )
    
    # ─────────────────────────────────────────────────────────────
    # Users Analytics (sin lista de usuarios)
    # ─────────────────────────────────────────────────────────────
    
    async def get_users_analytics(
        self,
        from_date: date,
        to_date: date,
    ) -> UsersAnalyticsMetrics:
        """
        Obtiene métricas analíticas de usuarios sin devolver lista individual.
        
        Métricas incluidas:
        - Periodo: creados, activados, eliminados
        - Stock: activados, activos, suspendidos, eliminados
        - Calidad: no activados >24h, p95 tiempo activación, reintentos
        - Conversión: tasa de activación, activados sin sesión
        - Estados críticos: suspendidos en periodo, eliminados sin activar
        """
        from_ts, to_ts = self._build_range(from_date, to_date)
        
        logger.info(
            "get_users_analytics from=%s to=%s",
            from_date, to_date
        )
        
        # Inicializar valores
        created_in_period = 0
        activated_in_period = 0
        deleted_in_period = 0
        activated_stock = 0
        active_stock = 0
        suspended_stock = 0
        deleted_stock = 0
        not_activated_24h = 0
        activation_time_p95_hours = None
        activation_retries = 0
        activation_retries_instrumented = False
        activation_rate = None
        activated_no_session = 0
        activated_no_session_in_period = 0
        suspended_created_in_period = 0
        deleted_not_activated = 0
        deleted_not_activated_in_period = 0
        
        # 1. Usuarios creados en el periodo
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.app_users
                WHERE user_created_at >= :from_ts
                  AND user_created_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                created_in_period = int(row[0])
        except Exception as e:
            logger.warning("users created_in_period failed: %s", e)
        
        # 2. Usuarios activados en el periodo
        try:
            q = text("""
                SELECT COUNT(DISTINCT user_id)
                FROM public.account_activations
                WHERE status = 'used'
                  AND consumed_at >= :from_ts
                  AND consumed_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                activated_in_period = int(row[0])
        except Exception as e:
            logger.debug("users activated_in_period failed: %s", e)
        
        # 3. Usuarios eliminados en el periodo
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.app_users
                WHERE deleted_at >= :from_ts
                  AND deleted_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                deleted_in_period = int(row[0])
        except Exception as e:
            logger.debug("users deleted_in_period failed: %s", e)
        
        # 4. Stock metrics (estado actual)
        try:
            q = text("""
                SELECT 
                    COUNT(*) FILTER (WHERE user_is_activated = true AND deleted_at IS NULL) as activated_stock,
                    COUNT(*) FILTER (WHERE deleted_at IS NULL AND (user_status IS NULL OR user_status != 'suspended')) as active_stock,
                    COUNT(*) FILTER (WHERE deleted_at IS NULL AND user_status = 'suspended') as suspended_stock,
                    COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) as deleted_stock
                FROM public.app_users
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row:
                activated_stock = int(row.activated_stock or 0)
                active_stock = int(row.active_stock or 0)
                suspended_stock = int(row.suspended_stock or 0)
                deleted_stock = int(row.deleted_stock or 0)
        except Exception as e:
            logger.warning("stock metrics failed: %s", e)
        
        # 5. Usuarios creados en periodo que NO activaron tras 24h
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.app_users u
                WHERE u.user_created_at >= :from_ts
                  AND u.user_created_at < :to_ts
                  AND u.user_is_activated = false
                  AND u.user_created_at < (NOW() - INTERVAL '24 hours')
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                not_activated_24h = int(row[0])
        except Exception as e:
            logger.debug("not_activated_24h failed: %s", e)
        
        # 6. Percentil 95 de tiempo de activación (en horas)
        try:
            q = text("""
                SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (
                    ORDER BY EXTRACT(EPOCH FROM (consumed_at - created_at)) / 3600.0
                ) as p95_hours
                FROM public.account_activations
                WHERE status = 'used'
                  AND consumed_at >= :from_ts
                  AND consumed_at < :to_ts
                  AND consumed_at > created_at
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row.p95_hours is not None:
                activation_time_p95_hours = round(float(row.p95_hours), 2)
        except Exception as e:
            logger.debug("activation_time_p95 failed: %s", e)
        
        # 7. Usuarios con reintentos de activación (>1 email) - depende de auth_email_events
        try:
            # Verificar si hay emails de activación ENVIADOS (mismo criterio que la métrica)
            q_check = text("""
                SELECT COUNT(*) FROM public.auth_email_events
                WHERE email_type = 'activation'
                  AND status = 'sent'
                  AND created_at >= :from_ts
                  AND created_at < :to_ts
            """)
            res_check = await self.db.execute(q_check, {"from_ts": from_ts, "to_ts": to_ts})
            check_row = res_check.first()
            has_email_events = check_row and check_row[0] and int(check_row[0]) > 0
            
            if has_email_events:
                activation_retries_instrumented = True
                q = text("""
                    SELECT COUNT(*)
                    FROM (
                        SELECT user_id
                        FROM public.auth_email_events
                        WHERE email_type = 'activation'
                          AND status = 'sent'
                          AND created_at >= :from_ts
                          AND created_at < :to_ts
                        GROUP BY user_id
                        HAVING COUNT(*) > 1
                    ) sub
                """)
                res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0]:
                    activation_retries = int(row[0])
        except Exception as e:
            logger.debug("activation_retries failed: %s", e)
        
        # 8. Tasa de activación del periodo
        if created_in_period > 0:
            activation_rate = round(activated_in_period / created_in_period, 4)
        
        # 9. Usuarios activados sin ninguna sesión (stock)
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.app_users u
                WHERE u.user_is_activated = true
                  AND u.deleted_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM public.user_sessions s WHERE s.user_id = u.user_id
                  )
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0]:
                activated_no_session = int(row[0])
        except Exception as e:
            logger.debug("activated_no_session failed: %s", e)
        
        # 9b. Activados en periodo sin sesión aún
        try:
            q = text("""
                SELECT COUNT(DISTINCT aa.user_id)
                FROM public.account_activations aa
                JOIN public.app_users u ON aa.user_id = u.user_id
                WHERE aa.status = 'used'
                  AND aa.consumed_at >= :from_ts
                  AND aa.consumed_at < :to_ts
                  AND u.deleted_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM public.user_sessions s WHERE s.user_id = aa.user_id
                  )
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                activated_no_session_in_period = int(row[0])
        except Exception as e:
            logger.debug("activated_no_session_in_period failed: %s", e)
        
        # 10. Suspendidos creados en el periodo
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.app_users
                WHERE user_created_at >= :from_ts
                  AND user_created_at < :to_ts
                  AND user_status = 'suspended'
                  AND deleted_at IS NULL
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                suspended_created_in_period = int(row[0])
        except Exception as e:
            logger.debug("suspended_created_in_period failed: %s", e)
        
        # 11. Eliminados sin activar (stock/histórico)
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.app_users
                WHERE deleted_at IS NOT NULL
                  AND user_is_activated = false
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0]:
                deleted_not_activated = int(row[0])
        except Exception as e:
            logger.debug("deleted_not_activated failed: %s", e)
        
        # 11b. Eliminados en periodo sin activar
        try:
            q = text("""
                SELECT COUNT(*)
                FROM public.app_users
                WHERE deleted_at >= :from_ts
                  AND deleted_at < :to_ts
                  AND user_is_activated = false
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0]:
                deleted_not_activated_in_period = int(row[0])
        except Exception as e:
            logger.debug("deleted_not_activated_in_period failed: %s", e)
        
        generated_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(
            "get_users_analytics completed: created=%d activated=%d rate=%s not24h=%d retries=%d instrumented=%s",
            created_in_period, activated_in_period, activation_rate, 
            not_activated_24h, activation_retries, activation_retries_instrumented
        )
        
        return UsersAnalyticsMetrics(
            created_in_period=created_in_period,
            activated_in_period=activated_in_period,
            deleted_in_period=deleted_in_period,
            activated_stock=activated_stock,
            active_stock=active_stock,
            suspended_stock=suspended_stock,
            deleted_stock=deleted_stock,
            not_activated_24h=not_activated_24h,
            activation_time_p95_hours=activation_time_p95_hours,
            activation_retries=activation_retries,
            activation_retries_instrumented=activation_retries_instrumented,
            activation_rate=activation_rate,
            activated_no_session=activated_no_session,
            activated_no_session_in_period=activated_no_session_in_period,
            suspended_created_in_period=suspended_created_in_period,
            deleted_not_activated=deleted_not_activated,
            deleted_not_activated_in_period=deleted_not_activated_in_period,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            generated_at=generated_at,
        )


# Fin del archivo
