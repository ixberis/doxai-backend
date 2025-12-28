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

    async def get_active_sessions(self) -> int:
        """
        Cuenta sesiones activas (no revocadas, no expiradas).
        Tabla: public.user_sessions
        Condición: revoked_at IS NULL AND expires_at > NOW()
        
        Intenta usar función SECURITY DEFINER si existe, 
        fallback a query directa, luego fallback a logins recientes.
        
        SIEMPRE retorna int (nunca None).
        """
        # Intentar función SECURITY DEFINER primero
        try:
            q = text("SELECT public.f_auth_active_sessions_count()")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                count = int(row[0])
                logger.debug("get_active_sessions source=function count=%d", count)
                return count
        except Exception as e:
            logger.debug("get_active_sessions function failed: %s", e)
        
        # Query directa sobre user_sessions
        try:
            q = text("""
                SELECT COUNT(*) 
                FROM public.user_sessions 
                WHERE revoked_at IS NULL 
                  AND expires_at > NOW()
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                count = int(row[0])
                if count > 0:
                    logger.debug("get_active_sessions source=user_sessions count=%d", count)
                    return count
        except Exception as e:
            logger.debug("get_active_sessions user_sessions failed: %s", e)
        
        # Fallback: contar usuarios con login reciente (últimos 15 minutos)
        try:
            q = text("""
                SELECT COUNT(DISTINCT user_id) 
                FROM public.app_users 
                WHERE user_last_login IS NOT NULL 
                  AND user_last_login > NOW() - INTERVAL '15 minutes'
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                count = int(row[0])
                logger.debug("get_active_sessions source=last_login_fallback count=%d", count)
                return count
        except Exception as e:
            logger.debug("get_active_sessions last_login_fallback failed: %s", e)
        
        logger.debug("get_active_sessions source=default_zero count=0")
        return 0

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
        """Cuenta usuarios distintos con al menos 1 pago exitoso."""
        try:
            q = text("SELECT COUNT(DISTINCT user_id) FROM public.payments WHERE status = 'succeeded'")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.debug("get_paying_users_total failed: %s", e)
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
