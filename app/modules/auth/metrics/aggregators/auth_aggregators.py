# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/auth_aggregators.py

Agregadores SQL para métricas del módulo Auth v2 (DB-first).

Estrategia:
- get_auth_metrics_snapshot_v2(): 1 query a vista consolidada
- get_active_sessions(): query separada (sesiones son tiempo real)
- Métodos individuales mantenidos como fallback

Consulta tablas/vistas reales del esquema DoxAI:
- public.v_auth_metrics_snapshot_v2 (vista consolidada)
- public.app_users (usuarios)
- public.user_sessions (sesiones)
- public.payments (pagos)

Autor: Ixchel Beristain
Fecha: 2025-11-07
Actualizado: 2025-12-28 - DB-first con vista v2
"""
from __future__ import annotations
import logging
from typing import Optional
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


logger = logging.getLogger(__name__)


@dataclass
class AuthMetricsSnapshotV2:
    """Dataclass para snapshot de métricas v2 desde vista SQL."""
    users_total: int
    users_deleted_total: int
    users_suspended_total: int
    users_current_total: int
    users_activated_total: int
    payments_paying_users_total: int
    auth_activation_conversion_ratio: float
    payments_conversion_ratio: float
    generated_at: str


class AuthAggregators:
    """
    Lógica de lectura/agregado desde tablas SQL reales.
    
    Estrategia v2 (DB-first):
    - get_auth_metrics_snapshot_v2(): 1 query a vista consolidada
    - get_active_sessions(): query separada (tiempo real)
    - Métodos individuales mantenidos como fallback
    
    IMPORTANTE: Métodos numéricos SIEMPRE retornan int/float (nunca None).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─────────────────────────────────────────────────────────────
    # NUEVO: Snapshot v2 desde vista (1 query)
    # ─────────────────────────────────────────────────────────────

    async def get_auth_metrics_snapshot_v2(self) -> Optional[AuthMetricsSnapshotV2]:
        """
        Obtiene todas las métricas de usuarios/pagos en 1 query.
        
        Consulta: SELECT * FROM public.v_auth_metrics_snapshot_v2
        
        Returns:
            AuthMetricsSnapshotV2 si la vista existe y retorna datos.
            None si la vista no existe o hay error.
        """
        try:
            q = text("SELECT * FROM public.v_auth_metrics_snapshot_v2")
            res = await self.db.execute(q)
            row = res.first()
            
            if row:
                return AuthMetricsSnapshotV2(
                    users_total=int(row.users_total or 0),
                    users_deleted_total=int(row.users_deleted_total or 0),
                    users_suspended_total=int(row.users_suspended_total or 0),
                    users_current_total=int(row.users_current_total or 0),
                    users_activated_total=int(row.users_activated_total or 0),
                    payments_paying_users_total=int(row.payments_paying_users_total or 0),
                    auth_activation_conversion_ratio=float(row.auth_activation_conversion_ratio or 0.0),
                    payments_conversion_ratio=float(row.payments_conversion_ratio or 0.0),
                    generated_at=str(row.generated_at) if row.generated_at else "",
                )
        except Exception as e:
            logger.warning("get_auth_metrics_snapshot_v2 failed (view may not exist): %s", e)
        
        return None

    # ─────────────────────────────────────────────────────────────
    # Métricas de sesiones (tabla: public.user_sessions)
    # ─────────────────────────────────────────────────────────────

    async def get_active_sessions_stats(self) -> tuple[int, int, float]:
        """
        Obtiene estadísticas completas de sesiones activas.
        
        Returns:
            Tuple (active_sessions_total, active_users_total, sessions_per_user_avg)
            - active_sessions_total: total de sesiones activas
            - active_users_total: usuarios únicos con al menos 1 sesión activa
            - sessions_per_user_avg: promedio de sesiones por usuario
        """
        # Intentar función SECURITY DEFINER primero
        try:
            q = text("SELECT * FROM public.f_auth_active_sessions_stats()")
            res = await self.db.execute(q)
            row = res.first()
            if row:
                sessions = int(row.active_sessions_total or 0)
                users = int(row.active_users_total or 0)
                avg = float(row.sessions_per_user_avg or 0.0)
                logger.debug(
                    "get_active_sessions_stats source=function sessions=%d users=%d avg=%.2f",
                    sessions, users, avg
                )
                return (sessions, users, avg)
        except Exception as e:
            logger.debug("get_active_sessions_stats function failed: %s", e)
        
        # Fallback: query directa
        try:
            q = text("""
                WITH s AS (
                    SELECT user_id
                    FROM public.user_sessions
                    WHERE revoked_at IS NULL
                      AND expires_at > NOW()
                )
                SELECT
                    (SELECT COUNT(*)::int FROM s) AS active_sessions_total,
                    (SELECT COUNT(DISTINCT user_id)::int FROM s) AS active_users_total
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row:
                sessions = int(row.active_sessions_total or 0)
                users = int(row.active_users_total or 0)
                avg = round(sessions / users, 2) if users > 0 else 0.0
                logger.debug(
                    "get_active_sessions_stats source=direct sessions=%d users=%d avg=%.2f",
                    sessions, users, avg
                )
                return (sessions, users, avg)
        except Exception as e:
            logger.debug("get_active_sessions_stats direct query failed: %s", e)
        
        return (0, 0, 0.0)

    async def get_active_sessions(self) -> int:
        """
        Cuenta sesiones activas (no revocadas, no expiradas).
        Wrapper de compatibilidad que usa get_active_sessions_stats().
        
        SIEMPRE retorna int (nunca None).
        """
        sessions, _, _ = await self.get_active_sessions_stats()
        return sessions

    # ─────────────────────────────────────────────────────────────
    # Métodos individuales (fallback si vista no existe)
    # ─────────────────────────────────────────────────────────────

    async def get_users_total(self) -> int:
        """Cuenta total de usuarios registrados (histórico)."""
        try:
            q = text("SELECT COUNT(*) FROM public.app_users")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.warning("get_users_total failed: %s", e)
        return 0

    async def get_users_deleted_total(self) -> int:
        """Cuenta usuarios eliminados (soft delete)."""
        try:
            q = text("SELECT COUNT(*) FROM public.app_users WHERE deleted_at IS NOT NULL")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.warning("get_users_deleted_total failed: %s", e)
        return 0

    async def get_users_suspended_total(self) -> int:
        """Cuenta usuarios suspendidos (vigentes, no eliminados)."""
        try:
            q = text("""
                SELECT COUNT(*) FROM public.app_users 
                WHERE user_status = 'suspended' AND deleted_at IS NULL
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.warning("get_users_suspended_total failed: %s", e)
        return 0

    async def get_users_current_total(self) -> int:
        """Cuenta usuarios vigentes (no eliminados, no suspendidos)."""
        try:
            q = text("""
                SELECT COUNT(*) FROM public.app_users 
                WHERE deleted_at IS NULL 
                  AND (user_status IS NULL OR user_status != 'suspended')
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.warning("get_users_current_total failed: %s", e)
        return 0

    async def get_users_activated_total(self) -> int:
        """
        Cuenta usuarios activados VIGENTES (no eliminados, no suspendidos).
        Consistente con vista v_auth_metrics_snapshot_v2.
        """
        try:
            q = text("""
                SELECT COUNT(*) FROM public.app_users 
                WHERE user_is_activated = true 
                  AND deleted_at IS NULL
                  AND (user_status IS NULL OR user_status != 'suspended')
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.warning("get_users_activated_total failed: %s", e)
        return 0

    async def get_paying_users_total(self) -> int:
        """
        Cuenta usuarios distintos con al menos 1 checkout completado.
        
        Fuente de verdad: billing.checkout_intents con status='completed'.
        Fallback: public.credit_transactions con operation_code='CHECKOUT'.
        """
        try:
            # Primary: checkout_intents with status='completed'
            q = text("""
                SELECT COUNT(DISTINCT user_id) 
                FROM billing.checkout_intents 
                WHERE status = 'completed'
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.debug("get_paying_users_total (checkout_intents) failed: %s", e)
        
        # Fallback: credit_transactions with operation_code='CHECKOUT'
        try:
            q = text("""
                SELECT COUNT(DISTINCT user_id) 
                FROM public.credit_transactions 
                WHERE operation_code = 'CHECKOUT'
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.debug("get_paying_users_total (credit_transactions) failed: %s", e)
        
        return 0

    async def get_activation_conversion_ratio(self) -> float:
        """Calcula ratio de conversión: users_activated / users_total."""
        users_total = await self.get_users_total()
        users_activated = await self.get_users_activated_total()
        if users_total > 0:
            return users_activated / users_total
        return 0.0

    async def get_payments_conversion_ratio(self) -> float:
        """Calcula ratio de conversión de pago: paying_users / users_activated."""
        users_activated = await self.get_users_activated_total()
        if users_activated == 0:
            return 0.0
        paying_users = await self.get_paying_users_total()
        return paying_users / users_activated

    async def get_latest_activation_conversion_ratio(self) -> float:
        """Obtiene el ratio más reciente de conversión registro→activación."""
        try:
            q = text("SELECT public.f_auth_activation_rate_latest()")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return float(row[0]) / 100.0
        except Exception as e:
            logger.debug("get_latest_activation_conversion_ratio function failed: %s", e)
        return await self.get_activation_conversion_ratio()

    # ─────────────────────────────────────────────────────────────
    # Helpers legacy
    # ─────────────────────────────────────────────────────────────

    async def get_login_attempts_hourly(self, p_from, p_to):
        """Devuelve lista de intentos de login por hora."""
        try:
            q = text("""
                SELECT ts_hour, success, reason, attempts
                FROM f_auth_login_attempts_hourly(:p_from, :p_to)
            """)
            res = await self.db.execute(q, {"p_from": p_from, "p_to": p_to})
            return res.fetchall()
        except Exception as e:
            logger.warning("get_login_attempts_hourly failed: %s", e)
            return []


# Fin del archivo backend/app/modules/auth/metrics/aggregators/auth_aggregators.py
