# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/operational_aggregators.py

Agregadores SQL para métricas operativas del módulo Auth.

Fuentes de datos:
- public.user_sessions: sesiones activas/creadas/expiradas/revocadas
- public.login_attempts: intentos de login, fallos por motivo
- public.auth_email_events: correos enviados/fallidos
- NO hay tabla de HTTP errors → retorna 0 con source=not_instrumented

Autor: Sistema
Fecha: 2026-01-03
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Import enum from central location for type-safe reason matching
from app.modules.auth.enums.login_failure_reason_enum import LoginFailureReason

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# Constants from LoginFailureReason enum
# ─────────────────────────────────────────────────────────────────
REASON_TOO_MANY_ATTEMPTS = LoginFailureReason.too_many_attempts.value
REASON_ACCOUNT_LOCKED = LoginFailureReason.account_locked.value


@dataclass
class OperationalSummaryData:
    """Data for operational summary endpoint."""
    # Sessions (real-time)
    sessions_active_total: int = 0
    sessions_active_users: int = 0
    sessions_per_user_avg: Optional[float] = None
    
    # Login attempts (period)
    login_attempts_total: int = 0
    login_attempts_failed: int = 0
    login_failure_rate: Optional[float] = None
    
    # Rate limits / lockouts (period)
    rate_limit_triggers: int = 0
    lockouts_total: int = 0
    
    # Emails (period)
    emails_sent_total: int = 0
    emails_failed_total: int = 0
    email_failure_rate: Optional[float] = None
    
    # Period
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    
    # Meta
    generated_at: str = ""


@dataclass
class TopUserSessions:
    """User with session count."""
    user_id: str
    user_email: str
    session_count: int


@dataclass
class SessionsDetailData:
    """Data for sessions detail endpoint."""
    # Real-time
    sessions_active_total: int = 0
    sessions_active_users: int = 0
    sessions_per_user_avg: Optional[float] = None
    
    # Period-based
    sessions_created: int = 0
    sessions_expired: int = 0
    sessions_revoked: int = 0
    
    # Top users
    top_users: List[TopUserSessions] = field(default_factory=list)
    
    # Period
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    
    # Meta
    generated_at: str = ""


@dataclass
class LoginFailureByReason:
    """Login failure count by reason."""
    reason: str
    count: int


@dataclass
class ErrorsDetailData:
    """Data for errors/friction endpoint."""
    # Login failures
    login_failures_by_reason: List[LoginFailureByReason] = field(default_factory=list)
    login_failures_total: int = 0
    
    # Rate limits
    rate_limit_triggers: int = 0
    rate_limit_by_ip: int = 0
    rate_limit_by_user: int = 0
    
    # Lockouts
    lockouts_total: int = 0
    lockouts_by_ip: int = 0
    lockouts_by_user: int = 0
    
    # HTTP errors (not instrumented)
    http_4xx_count: int = 0
    http_5xx_count: int = 0
    
    # Period
    period_from: Optional[str] = None
    period_to: Optional[str] = None
    
    # Meta
    generated_at: str = ""


class OperationalAggregators:
    """
    Agregadores para métricas operativas de Auth.
    
    Separación Operativo vs Funcional:
    - Operativo: infraestructura, fricción, entregabilidad
    - Funcional: negocio, conversión, usuarios
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ─────────────────────────────────────────────────────────────
    # ENDPOINT 1: Operational Summary
    # ─────────────────────────────────────────────────────────────
    
    async def get_operational_summary(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> OperationalSummaryData:
        """
        Obtiene resumen operativo.
        
        - Sessions: real-time (ignora rango)
        - Login attempts, emails: respetan rango
        """
        result = OperationalSummaryData(
            period_from=from_date,
            period_to=to_date,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        
        # 1) Sessions (real-time)
        sessions, users, avg = await self._get_active_sessions_stats()
        result.sessions_active_total = sessions
        result.sessions_active_users = users
        result.sessions_per_user_avg = avg
        logger.debug(
            "get_operational_summary source=user_sessions "
            f"sessions={sessions} users={users} avg={avg}"
        )
        
        # 2) Login attempts (period)
        login_total, login_failed = await self._get_login_attempts(from_date, to_date)
        result.login_attempts_total = login_total
        result.login_attempts_failed = login_failed
        result.login_failure_rate = (
            round(login_failed / login_total, 4) if login_total > 0 else None
        )
        logger.debug(
            "get_operational_summary source=login_attempts "
            f"total={login_total} failed={login_failed}"
        )
        
        # 3) Rate limits and lockouts (period)
        rate_limits, lockouts = await self._get_rate_limits_and_lockouts(from_date, to_date)
        result.rate_limit_triggers = rate_limits
        result.lockouts_total = lockouts
        logger.debug(
            "get_operational_summary source=login_attempts(rate_limit) "
            f"rate_limits={rate_limits} lockouts={lockouts}"
        )
        
        # 4) Emails (period)
        sent, failed = await self._get_email_counts(from_date, to_date)
        result.emails_sent_total = sent
        result.emails_failed_total = failed
        total_attempts = sent + failed
        result.email_failure_rate = (
            round(failed / total_attempts, 4) if total_attempts > 0 else None
        )
        logger.debug(
            "get_operational_summary source=auth_email_events "
            f"sent={sent} failed={failed}"
        )
        
        return result
    
    # ─────────────────────────────────────────────────────────────
    # ENDPOINT 2: Sessions Detail
    # ─────────────────────────────────────────────────────────────
    
    async def get_sessions_detail(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
        limit: int = 10,
    ) -> SessionsDetailData:
        """
        Obtiene detalle de sesiones.
        
        - Real-time: activas, usuarios, promedio
        - Period: creadas, expiradas, revocadas
        - Top users: ordenados por # sesiones activas
        """
        result = SessionsDetailData(
            period_from=from_date,
            period_to=to_date,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        
        # 1) Real-time
        sessions, users, avg = await self._get_active_sessions_stats()
        result.sessions_active_total = sessions
        result.sessions_active_users = users
        result.sessions_per_user_avg = avg
        
        # 2) Period-based
        created, expired, revoked = await self._get_sessions_period(from_date, to_date)
        result.sessions_created = created
        result.sessions_expired = expired
        result.sessions_revoked = revoked
        logger.debug(
            "get_sessions_detail source=user_sessions "
            f"created={created} expired={expired} revoked={revoked}"
        )
        
        # 3) Top users
        result.top_users = await self._get_top_users_by_sessions(limit)
        logger.debug(
            f"get_sessions_detail source=user_sessions top_users_count={len(result.top_users)}"
        )
        
        return result
    
    # ─────────────────────────────────────────────────────────────
    # ENDPOINT 3: Errors Detail
    # ─────────────────────────────────────────────────────────────
    
    async def get_errors_detail(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> ErrorsDetailData:
        """
        Obtiene detalle de errores/fricción.
        
        - Login failures by reason
        - Rate limits by IP/user
        - Lockouts by IP/user
        - HTTP errors (not instrumented)
        """
        result = ErrorsDetailData(
            period_from=from_date,
            period_to=to_date,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        
        # 1) Login failures by reason
        failures_by_reason = await self._get_login_failures_by_reason(from_date, to_date)
        result.login_failures_by_reason = failures_by_reason
        result.login_failures_total = sum(f.count for f in failures_by_reason)
        logger.debug(
            "get_errors_detail source=login_attempts "
            f"failures_total={result.login_failures_total} reasons={len(failures_by_reason)}"
        )
        
        # 2) Rate limits (from login_attempts with reason='too_many_attempts')
        rate_by_ip, rate_by_user = await self._get_rate_limit_breakdown(from_date, to_date)
        result.rate_limit_by_ip = rate_by_ip
        result.rate_limit_by_user = rate_by_user
        result.rate_limit_triggers = rate_by_ip + rate_by_user
        logger.debug(
            "get_errors_detail source=login_attempts(too_many_attempts) "
            f"by_ip={rate_by_ip} by_user={rate_by_user}"
        )
        
        # 3) Lockouts (from login_attempts with reason='account_locked')
        lock_by_ip, lock_by_user = await self._get_lockout_breakdown(from_date, to_date)
        result.lockouts_by_ip = lock_by_ip
        result.lockouts_by_user = lock_by_user
        result.lockouts_total = lock_by_ip + lock_by_user
        logger.debug(
            "get_errors_detail source=login_attempts(account_locked) "
            f"by_ip={lock_by_ip} by_user={lock_by_user}"
        )
        
        # 4) HTTP errors - NOT INSTRUMENTED
        result.http_4xx_count = 0
        result.http_5xx_count = 0
        logger.debug("get_errors_detail source=not_instrumented http_4xx=0 http_5xx=0")
        
        return result
    
    # ─────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────
    
    async def _get_active_sessions_stats(self) -> tuple[int, int, Optional[float]]:
        """Get active sessions stats (real-time)."""
        try:
            # Try function first
            q = text("SELECT * FROM public.f_auth_active_sessions_stats()")
            res = await self.db.execute(q)
            row = res.first()
            if row:
                sessions = int(row.active_sessions_total or 0)
                users = int(row.active_users_total or 0)
                avg = float(row.sessions_per_user_avg or 0.0) if users > 0 else None
                return (sessions, users, avg)
        except Exception as e:
            logger.debug(f"f_auth_active_sessions_stats failed: {e}")
        
        # Fallback: direct query
        try:
            q = text("""
                WITH s AS (
                    SELECT user_id
                    FROM public.user_sessions
                    WHERE revoked_at IS NULL AND expires_at > NOW()
                )
                SELECT
                    (SELECT COUNT(*)::int FROM s) AS sessions,
                    (SELECT COUNT(DISTINCT user_id)::int FROM s) AS users
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row:
                sessions = int(row.sessions or 0)
                users = int(row.users or 0)
                avg = round(sessions / users, 2) if users > 0 else None
                return (sessions, users, avg)
        except Exception as e:
            logger.warning(f"_get_active_sessions_stats failed: {e}")
        
        return (0, 0, None)
    
    def _build_period_filter(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
        col: str = "created_at",
    ) -> tuple[str, Dict[str, Any]]:
        """Build half-open period filter clause."""
        if from_date and to_date:
            return (
                f"AND {col} >= :from_date::date AND {col} < (:to_date::date + interval '1 day')",
                {"from_date": from_date, "to_date": to_date}
            )
        return ("", {})
    
    async def _get_login_attempts(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> tuple[int, int]:
        """Get login attempts total and failed."""
        filter_clause, params = self._build_period_filter(from_date, to_date)
        
        try:
            q = text(f"""
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE NOT success)::int AS failed
                FROM public.login_attempts
                WHERE 1=1 {filter_clause}
            """)
            res = await self.db.execute(q, params)
            row = res.first()
            if row:
                return (int(row.total or 0), int(row.failed or 0))
        except Exception as e:
            logger.warning(f"_get_login_attempts failed: {e}")
        
        return (0, 0)
    
    async def _get_rate_limits_and_lockouts(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> tuple[int, int]:
        """
        Get rate limit triggers and lockouts count.
        
        Uses LoginFailureReason enum values for type-safe matching.
        If reasons don't exist in DB, returns 0 and logs source=not_instrumented_reason.
        """
        filter_clause, params = self._build_period_filter(from_date, to_date)
        params["reason_rate_limit"] = REASON_TOO_MANY_ATTEMPTS
        params["reason_lockout"] = REASON_ACCOUNT_LOCKED
        
        try:
            q = text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE reason = :reason_rate_limit)::int AS rate_limits,
                    COUNT(*) FILTER (WHERE reason = :reason_lockout)::int AS lockouts
                FROM public.login_attempts
                WHERE NOT success {filter_clause}
            """)
            res = await self.db.execute(q, params)
            row = res.first()
            if row:
                rate_limits = int(row.rate_limits or 0)
                lockouts = int(row.lockouts or 0)
                
                # Log with semantic distinction: no_events_in_period (query OK, count 0)
                if rate_limits == 0:
                    logger.debug(
                        f"_get_rate_limits_and_lockouts source=login_attempts "
                        f"reason={REASON_TOO_MANY_ATTEMPTS} count=0 note=no_events_in_period"
                    )
                if lockouts == 0:
                    logger.debug(
                        f"_get_rate_limits_and_lockouts source=login_attempts "
                        f"reason={REASON_ACCOUNT_LOCKED} count=0 note=no_events_in_period"
                    )
                
                return (rate_limits, lockouts)
        except Exception as e:
            logger.warning(f"_get_rate_limits_and_lockouts failed: {e}")
        
        return (0, 0)
    
    async def _get_email_counts(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> tuple[int, int]:
        """Get email sent and failed counts from auth_email_events."""
        filter_clause, params = self._build_period_filter(from_date, to_date)
        
        try:
            q = text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'sent')::int AS sent,
                    COUNT(*) FILTER (WHERE status = 'failed')::int AS failed
                FROM public.auth_email_events
                WHERE 1=1 {filter_clause}
            """)
            res = await self.db.execute(q, params)
            row = res.first()
            if row:
                return (int(row.sent or 0), int(row.failed or 0))
        except Exception as e:
            logger.warning(f"_get_email_counts failed: {e}")
        
        return (0, 0)
    
    async def _get_sessions_period(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> tuple[int, int, int]:
        """
        Get sessions created/expired/revoked in period.
        
        Definitions:
        - created: issued_at in range [from, to+1)
        - revoked: revoked_at in range [from, to+1)
        - expired: expires_at in range [from, to+1) AND revoked_at IS NULL AND expires_at <= NOW()
        
        Uses half-open UTC range.
        """
        params: Dict[str, Any] = {}
        
        if from_date and to_date:
            params = {"from_date": from_date, "to_date": to_date}
            
            try:
                q = text("""
                    SELECT
                        (SELECT COUNT(*)::int 
                         FROM public.user_sessions 
                         WHERE issued_at >= :from_date::date 
                           AND issued_at < (:to_date::date + interval '1 day')
                        ) AS created,
                        (SELECT COUNT(*)::int 
                         FROM public.user_sessions 
                         WHERE expires_at >= :from_date::date 
                           AND expires_at < (:to_date::date + interval '1 day')
                           AND revoked_at IS NULL 
                           AND expires_at <= NOW()
                        ) AS expired,
                        (SELECT COUNT(*)::int 
                         FROM public.user_sessions 
                         WHERE revoked_at >= :from_date::date 
                           AND revoked_at < (:to_date::date + interval '1 day')
                        ) AS revoked
                """)
                res = await self.db.execute(q, params)
                row = res.first()
                if row:
                    logger.debug(
                        f"_get_sessions_period source=user_sessions "
                        f"range=[{from_date}, {to_date}+1) "
                        f"created={row.created} expired={row.expired} revoked={row.revoked}"
                    )
                    return (int(row.created or 0), int(row.expired or 0), int(row.revoked or 0))
            except Exception as e:
                logger.warning(f"_get_sessions_period failed: {e}")
            
            return (0, 0, 0)
        
        # No date range: return zeros
        logger.debug("_get_sessions_period source=user_sessions no_range=true returning zeros")
        return (0, 0, 0)
    
    async def _get_top_users_by_sessions(self, limit: int = 10) -> List[TopUserSessions]:
        """Get top users by active session count."""
        try:
            q = text("""
                SELECT 
                    u.user_id::text AS user_id,
                    u.user_email,
                    COUNT(s.id)::int AS session_count
                FROM public.app_users u
                JOIN public.user_sessions s ON s.user_id = u.user_id
                WHERE s.revoked_at IS NULL AND s.expires_at > NOW()
                GROUP BY u.user_id, u.user_email
                ORDER BY session_count DESC
                LIMIT :limit
            """)
            res = await self.db.execute(q, {"limit": limit})
            rows = res.fetchall()
            
            return [
                TopUserSessions(
                    user_id=str(row.user_id),
                    user_email=row.user_email or "",
                    session_count=int(row.session_count),
                )
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"_get_top_users_by_sessions failed: {e}")
        
        return []
    
    async def _get_login_failures_by_reason(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> List[LoginFailureByReason]:
        """Get login failures grouped by reason."""
        filter_clause, params = self._build_period_filter(from_date, to_date)
        
        try:
            q = text(f"""
                SELECT 
                    COALESCE(reason::text, 'unknown') AS reason,
                    COUNT(*)::int AS count
                FROM public.login_attempts
                WHERE NOT success {filter_clause}
                GROUP BY reason
                ORDER BY count DESC
            """)
            res = await self.db.execute(q, params)
            rows = res.fetchall()
            
            return [
                LoginFailureByReason(
                    reason=row.reason or "unknown",
                    count=int(row.count),
                )
                for row in rows
            ]
        except Exception as e:
            logger.warning(f"_get_login_failures_by_reason failed: {e}")
        
        return []
    
    async def _get_rate_limit_breakdown(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> tuple[int, int]:
        """
        Get rate limit triggers broken down by IP vs user.
        
        Logic:
        - by_user: user_id IS NOT NULL (user-identified rate limit)
        - by_ip: user_id IS NULL AND ip_address IS NOT NULL (IP-only rate limit)
        
        Uses LoginFailureReason enum for type-safe matching.
        """
        filter_clause, params = self._build_period_filter(from_date, to_date)
        params["reason_rate_limit"] = REASON_TOO_MANY_ATTEMPTS
        
        try:
            q = text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE user_id IS NOT NULL)::int AS by_user,
                    COUNT(*) FILTER (WHERE user_id IS NULL AND ip_address IS NOT NULL)::int AS by_ip
                FROM public.login_attempts
                WHERE NOT success AND reason = :reason_rate_limit {filter_clause}
            """)
            res = await self.db.execute(q, params)
            row = res.first()
            if row:
                by_user = int(row.by_user or 0)
                by_ip = int(row.by_ip or 0)
                
                if by_user == 0 and by_ip == 0:
                    logger.debug(
                        f"_get_rate_limit_breakdown source=login_attempts "
                        f"reason={REASON_TOO_MANY_ATTEMPTS} by_user=0 by_ip=0 "
                        "note=no_events_in_period"
                    )
                
                return (by_ip, by_user)
        except Exception as e:
            logger.warning(f"_get_rate_limit_breakdown failed: {e}")
        
        return (0, 0)
    
    async def _get_lockout_breakdown(
        self,
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> tuple[int, int]:
        """
        Get lockout counts broken down by IP vs user.
        
        Logic:
        - by_user: user_id IS NOT NULL (user-identified lockout)
        - by_ip: user_id IS NULL AND ip_address IS NOT NULL (IP-only lockout)
        
        Uses LoginFailureReason enum for type-safe matching.
        """
        filter_clause, params = self._build_period_filter(from_date, to_date)
        params["reason_lockout"] = REASON_ACCOUNT_LOCKED
        
        try:
            q = text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE user_id IS NOT NULL)::int AS by_user,
                    COUNT(*) FILTER (WHERE user_id IS NULL AND ip_address IS NOT NULL)::int AS by_ip
                FROM public.login_attempts
                WHERE NOT success AND reason = :reason_lockout {filter_clause}
            """)
            res = await self.db.execute(q, params)
            row = res.first()
            if row:
                by_user = int(row.by_user or 0)
                by_ip = int(row.by_ip or 0)
                
                if by_user == 0 and by_ip == 0:
                    logger.debug(
                        f"_get_lockout_breakdown source=login_attempts "
                        f"reason={REASON_ACCOUNT_LOCKED} by_user=0 by_ip=0 "
                        "note=no_events_in_period"
                    )
                
                return (by_ip, by_user)
        except Exception as e:
            logger.warning(f"_get_lockout_breakdown failed: {e}")
        
        return (0, 0)


# Fin del archivo
