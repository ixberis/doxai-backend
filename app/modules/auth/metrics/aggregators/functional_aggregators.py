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
class UserListItem:
    """Usuario para tabla de usuarios."""
    user_id: str
    email_masked: str
    full_name: Optional[str]
    status: str  # active, suspended, deleted
    is_activated: bool
    created_at: str
    activated_at: Optional[str]
    last_login_at: Optional[str]


@dataclass
class UsersMetrics:
    """Métricas de usuarios por rango con paginación."""
    users: List[UserListItem]
    total: int
    page: int
    page_size: int
    # Totals for period
    created_in_period: int
    activated_in_period: int
    deleted_in_period: int
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
        - public.account_activations (activaciones, reenvíos, expirados)
        - public.auth_email_events (emails enviados de tipo activation)
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
        
        # 1. Emails de activación enviados en el periodo (desde auth_email_events)
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
                activation_emails_sent = int(row[0])
        except Exception as e:
            logger.debug("activation_emails_sent failed: %s", e)
            # Fallback: usar account_activations.activation_email_sent_at
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
                    activation_emails_sent = int(row[0])
            except Exception as e2:
                logger.warning("activation_emails_sent fallback failed: %s", e2)
        
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
        try:
            q = text("""
                SELECT COALESCE(SUM(cnt - 1), 0)
                FROM (
                    SELECT user_id, COUNT(*) as cnt
                    FROM public.auth_email_events
                    WHERE email_type = 'account_activation'
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
            "get_activation_metrics completed: emails=%d completed=%d resends=%d expired=%d rate=%s avg=%s",
            activation_emails_sent, activations_completed, resends, tokens_expired,
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
    # Users List (Paginada)
    # ─────────────────────────────────────────────────────────────
    
    async def get_users_in_period(
        self,
        from_date: date,
        to_date: date,
        page: int = 1,
        page_size: int = 50,
    ) -> UsersMetrics:
        """
        Obtiene lista paginada de usuarios creados en el periodo.
        
        Email enmascarado para privacidad.
        """
        from_ts, to_ts = self._build_range(from_date, to_date)
        offset = (page - 1) * page_size
        
        logger.info(
            "get_users_in_period from=%s to=%s page=%d page_size=%d",
            from_date, to_date, page, page_size
        )
        
        users: List[UserListItem] = []
        total = 0
        created_in_period = 0
        activated_in_period = 0
        deleted_in_period = 0
        
        # 1. Total de usuarios creados en el periodo
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
                total = int(row[0])
                created_in_period = total
        except Exception as e:
            logger.warning("users total failed: %s", e)
        
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
        
        # 4. Lista paginada de usuarios
        try:
            q = text("""
                SELECT 
                    user_id::text,
                    user_email,
                    user_full_name,
                    user_status,
                    user_is_activated,
                    user_created_at::text,
                    user_activated_at::text,
                    user_last_login::text,
                    deleted_at::text
                FROM public.app_users
                WHERE user_created_at >= :from_ts
                  AND user_created_at < :to_ts
                ORDER BY user_created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            res = await self.db.execute(q, {
                "from_ts": from_ts,
                "to_ts": to_ts,
                "limit": page_size,
                "offset": offset,
            })
            rows = res.fetchall()
            
            for row in rows:
                # Determinar status
                status = 'active'
                if row.deleted_at:
                    status = 'deleted'
                elif row.user_status == 'suspended':
                    status = 'suspended'
                
                users.append(UserListItem(
                    user_id=str(row.user_id),
                    email_masked=self._mask_email(row.user_email or ''),
                    full_name=row.user_full_name,
                    status=status,
                    is_activated=bool(row.user_is_activated),
                    created_at=row.user_created_at or '',
                    activated_at=row.user_activated_at,
                    last_login_at=row.user_last_login,
                ))
        except Exception as e:
            logger.warning("users list failed: %s", e)
        
        generated_at = datetime.now(timezone.utc).isoformat()
        
        logger.info(
            "get_users_in_period completed: total=%d page=%d users=%d",
            total, page, len(users)
        )
        
        return UsersMetrics(
            users=users,
            total=total,
            page=page,
            page_size=page_size,
            created_in_period=created_in_period,
            activated_in_period=activated_in_period,
            deleted_in_period=deleted_in_period,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            generated_at=generated_at,
        )


# Fin del archivo
