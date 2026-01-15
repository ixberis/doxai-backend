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
from datetime import date, datetime, timezone, time, timedelta
from typing import Optional, Union
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


logger = logging.getLogger(__name__)


@dataclass
class AuthSummaryData:
    """
    Dataclass para resumen con rango de fechas.
    
    NOTA TZ: Las fechas (from_date, to_date) se interpretan en UTC.
    Los rangos usan comparación half-open: [from_date 00:00 UTC, to_date+1 00:00 UTC).
    """
    users_created: int
    users_activated: int
    users_paying: int
    creation_to_activation_ratio: Optional[float]
    activation_to_payment_ratio: Optional[float]
    creation_to_payment_ratio: Optional[float]
    from_date: str
    to_date: str
    generated_at: str


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
        
        SSOT BD 2.0: auth_user_id (UUID) - NO user_id.
        
        Fuente primaria: public.checkout_intents con status='completed'.
        Fallback: public.credit_transactions con operation_code='CHECKOUT'
                  (canónico: BillingFinalizeService usa 'CHECKOUT' al completar).
        """
        try:
            q = text("""
                SELECT COUNT(DISTINCT auth_user_id) 
                FROM public.checkout_intents 
                WHERE status = 'completed'
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.debug("get_paying_users_total primary failed: %s", e)
            try:
                await self.db.rollback()
            except Exception:
                pass
        
        # Fallback: credit_transactions.operation_code='CHECKOUT' (canónico)
        try:
            q = text("""
                SELECT COUNT(DISTINCT auth_user_id) 
                FROM public.credit_transactions 
                WHERE operation_code = 'CHECKOUT'
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.debug("get_paying_users_total fallback failed: %s", e)
        
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
    # NUEVO: Summary con rango de fechas
    # ─────────────────────────────────────────────────────────────

    # Version marker for production debugging
    AUTH_SUMMARY_VERSION = "from_ts_to_ts_v1"

    async def get_auth_summary(
        self, from_date: Union[str, date], to_date: Union[str, date]
    ) -> AuthSummaryData:
        """
        Obtiene resumen de métricas Auth dentro de un rango de fechas.
        
        Args:
            from_date: Fecha inicio (YYYY-MM-DD o date) - inclusive
            to_date: Fecha fin (YYYY-MM-DD o date) - inclusive
            
        Returns:
            AuthSummaryData con counts y ratios para el rango.
        """
        # Parsear strings a datetime UTC para evitar errores asyncpg:
        # 1. "invalid input for query argument: 'str' object has no attribute 'toordinal'"
        # 2. "operator does not exist: timestamp with time zone < interval"
        # Construimos datetime tz-aware directamente, sin depender de interval en SQL.
        # Soportar str o date (patrón canónico temporal)
        from_dt = (
            datetime.strptime(from_date, "%Y-%m-%d").date()
            if isinstance(from_date, str)
            else from_date
        )
        to_dt = (
            datetime.strptime(to_date, "%Y-%m-%d").date()
            if isinstance(to_date, str)
            else to_date
        )
        
        # Half-open range: [from_ts, to_ts) donde to_ts = to_dt + 1 day a las 00:00 UTC
        from_ts = datetime.combine(from_dt, time.min, tzinfo=timezone.utc)
        to_ts = datetime.combine(to_dt + timedelta(days=1), time.min, tzinfo=timezone.utc)
        
        # Log version and types for production debugging
        logger.info(
            "get_auth_summary AUTH_SUMMARY_VERSION=%s from_date=%s to_date=%s "
            "from_ts=%s (type=%s, tzinfo=%s) to_ts=%s (type=%s, tzinfo=%s)",
            self.AUTH_SUMMARY_VERSION,
            from_date, to_date,
            from_ts, type(from_ts).__name__, from_ts.tzinfo,
            to_ts, type(to_ts).__name__, to_ts.tzinfo
        )
        
        users_created = 0
        users_activated = 0
        users_paying = 0
        activated_source = "none"
        paying_source = "none"
        
        # Query usuarios creados en el rango (half-open: >= from_ts, < to_ts)
        # Fuente: public.app_users.user_created_at
        try:
            q = text("""
                SELECT COUNT(*) 
                FROM public.app_users 
                WHERE user_created_at >= :from_ts 
                  AND user_created_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0] is not None:
                users_created = int(row[0])
                logger.debug(
                    "get_auth_summary users_created=%d source=app_users.user_created_at",
                    users_created
                )
        except Exception as e:
            logger.warning("get_auth_summary users_created failed: %s", e)
        
        # Query usuarios activados en el rango
        # Fuente primaria: public.account_activations.consumed_at (status='consumed')
        # CANONICAL: status='consumed' is the only valid value for completed activations
        # Fallback: public.app_users.user_activated_at
        try:
            q = text("""
                SELECT COUNT(DISTINCT user_id)
                FROM public.account_activations
                WHERE status = 'consumed'
                  AND consumed_at IS NOT NULL
                  AND consumed_at >= :from_ts
                  AND consumed_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0] is not None:
                users_activated = int(row[0])
                activated_source = "account_activations.consumed_at"
                logger.debug(
                    "get_auth_summary users_activated=%d source=%s",
                    users_activated, activated_source
                )
        except Exception as e:
            logger.debug("get_auth_summary account_activations query failed, trying fallback: %s", e)
            # CRITICAL: Rollback para evitar InFailedSQLTransactionError en fallback
            try:
                await self.db.rollback()
            except Exception:
                pass  # Ignorar errores de rollback
            
            # Fallback: usar app_users.user_activated_at
            try:
                q_fallback = text("""
                    SELECT COUNT(*) 
                    FROM public.app_users 
                    WHERE user_activated_at IS NOT NULL
                      AND user_activated_at >= :from_ts
                      AND user_activated_at < :to_ts
                """)
                res = await self.db.execute(q_fallback, {"from_ts": from_ts, "to_ts": to_ts})
                row = res.first()
                if row and row[0] is not None:
                    users_activated = int(row[0])
                    activated_source = "app_users.user_activated_at"
                    logger.debug(
                        "get_auth_summary users_activated=%d source=%s (fallback)",
                        users_activated, activated_source
                    )
            except Exception as e2:
                logger.warning("get_auth_summary users_activated fallback failed: %s", e2)
        
        # Query usuarios con pago en el rango
        # Fuente: public.checkout_intents.completed_at (status='completed')
        # SSOT BD 2.0: auth_user_id (UUID), NOT user_id
        try:
            q = text("""
                SELECT COUNT(DISTINCT auth_user_id)
                FROM public.checkout_intents
                WHERE status = 'completed'
                  AND completed_at IS NOT NULL
                  AND completed_at >= :from_ts
                  AND completed_at < :to_ts
            """)
            res = await self.db.execute(q, {"from_ts": from_ts, "to_ts": to_ts})
            row = res.first()
            if row and row[0] is not None:
                users_paying = int(row[0])
                paying_source = "checkout_intents.completed_at"
                logger.debug(
                    "get_auth_summary users_paying=%d source=%s",
                    users_paying, paying_source
                )
        except Exception as e:
            logger.warning("get_auth_summary users_paying failed: %s", e)
        
        # Calcular ratios (None si denominador = 0)
        creation_to_activation_ratio = (
            round(users_activated / users_created, 4) if users_created > 0 else None
        )
        activation_to_payment_ratio = (
            round(users_paying / users_activated, 4) if users_activated > 0 else None
        )
        creation_to_payment_ratio = (
            round(users_paying / users_created, 4) if users_created > 0 else None
        )
        
        generated_at = datetime.now(timezone.utc).isoformat()
        
        # Helper para loguear None como "null" (no convertir a 0)
        def _ratio_str(v: Optional[float]) -> str:
            return f"{v:.4f}" if v is not None else "null"
        
        logger.info(
            "[auth_metrics_summary] from=%s to=%s users_created=%d users_activated=%d "
            "users_paying=%d source_activated=%s source_paying=%s "
            "ratios=(%s, %s, %s) generated_at=%s",
            from_date, to_date, users_created, users_activated, users_paying,
            activated_source, paying_source,
            _ratio_str(creation_to_activation_ratio),
            _ratio_str(activation_to_payment_ratio),
            _ratio_str(creation_to_payment_ratio),
            generated_at
        )
        
        return AuthSummaryData(
            users_created=users_created,
            users_activated=users_activated,
            users_paying=users_paying,
            creation_to_activation_ratio=creation_to_activation_ratio,
            activation_to_payment_ratio=activation_to_payment_ratio,
            creation_to_payment_ratio=creation_to_payment_ratio,
            from_date=from_date,
            to_date=to_date,
            generated_at=generated_at,
        )

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
