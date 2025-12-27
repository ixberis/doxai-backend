# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/auth_aggregators.py

Agregadores SQL para métricas del módulo Auth.

Consulta tablas reales del esquema DoxAI:
- public.app_users (usuarios)
- public.user_sessions (sesiones)
- public.payments (pagos)

Autor: Ixchel Beristain
Fecha: 2025-11-07
Actualizado: 2025-12-27 - Siempre retorna int (nunca None), logging de fuente
"""
from __future__ import annotations
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA REAL (EVIDENCIA)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Tabla: public.app_users
#   - user_id (PK, int)
#   - user_is_activated (bool) ← campo real de activación
#   - user_activated_at (timestamp, nullable)
#   - user_last_login (timestamp, nullable) ← último login
#
# Tabla: public.user_sessions
#   - id (PK)
#   - user_id (FK → app_users.user_id)
#   - revoked_at (timestamp, nullable) ← NULL = no revocada
#   - expires_at (timestamp) ← sesión activa si > NOW()
#
# Tabla: public.payments
#   - id (PK)
#   - user_id (FK → app_users.user_id)
#   - status (payment_status_enum) ← 'succeeded' = pago exitoso
#
# ═══════════════════════════════════════════════════════════════════════════════


class AuthAggregators:
    """
    Lógica de lectura/agregado desde tablas SQL reales.
    Estos métodos devuelven valores crudos que pueden
    ser usados por exportadores o dashboards internos.
    
    IMPORTANTE: Métodos numéricos SIEMPRE retornan int (nunca None).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─────────────────────────────────────────────────────────────
    # Métricas de usuarios (tabla: public.app_users)
    # ─────────────────────────────────────────────────────────────

    async def get_users_total(self) -> int:
        """
        Cuenta total de usuarios registrados.
        Tabla: public.app_users
        """
        try:
            q = text("SELECT COUNT(*) FROM public.app_users")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.warning("get_users_total failed: %s", e)
        return 0

    async def get_users_activated_total(self) -> int:
        """
        Cuenta usuarios con cuenta activada.
        Tabla: public.app_users
        Columna: user_is_activated (bool)
        """
        try:
            q = text("""
                SELECT COUNT(*) FROM public.app_users 
                WHERE user_is_activated = true
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.warning("get_users_activated_total failed: %s", e)
        return 0

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
        # Esto funciona como proxy cuando user_sessions no tiene datos
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

    async def get_active_users_total(self) -> int:
        """
        Cuenta usuarios distintos con sesión activa.
        Tabla: public.user_sessions
        Condición: revoked_at IS NULL AND expires_at > NOW()
        
        Fallback a logins recientes si user_sessions no tiene datos.
        
        SIEMPRE retorna int (nunca None).
        """
        # Query directa sobre user_sessions
        try:
            q = text("""
                SELECT COUNT(DISTINCT user_id) 
                FROM public.user_sessions 
                WHERE revoked_at IS NULL 
                  AND expires_at > NOW()
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                count = int(row[0])
                if count > 0:
                    logger.debug("get_active_users_total source=user_sessions count=%d", count)
                    return count
        except Exception as e:
            logger.debug("get_active_users_total user_sessions failed: %s", e)
        
        # Fallback: usuarios con login reciente (últimos 15 minutos)
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
                logger.debug("get_active_users_total source=last_login_fallback count=%d", count)
                return count
        except Exception as e:
            logger.debug("get_active_users_total last_login_fallback failed: %s", e)
        
        logger.debug("get_active_users_total source=default_zero count=0")
        return 0

    # ─────────────────────────────────────────────────────────────
    # Métricas de conversión
    # ─────────────────────────────────────────────────────────────

    async def get_latest_activation_conversion_ratio(self) -> float:
        """
        Obtiene el ratio más reciente de conversión registro→activación.
        Intenta usar función SECURITY DEFINER si existe.
        Returns ratio (0-1), not percentage. Frontend multiplies by 100.
        
        SIEMPRE retorna float (nunca None).
        """
        try:
            q = text("SELECT public.f_auth_activation_rate_latest()")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                # SQL returns percentage (e.g., 11.11), convert to ratio (0.1111)
                return float(row[0]) / 100.0
        except Exception as e:
            logger.debug("get_latest_activation_conversion_ratio function failed: %s", e)
        
        # Fallback calculado
        ratio = await self.get_activation_conversion_ratio()
        return ratio

    async def get_activation_conversion_ratio(self) -> float:
        """
        Calcula ratio de conversión: users_activated / users_total.
        Fallback si la función SQL no existe.
        
        SIEMPRE retorna float (nunca None).
        """
        users_total = await self.get_users_total()
        users_activated = await self.get_users_activated_total()
        
        if users_total > 0:
            return users_activated / users_total
        return 0.0

    # ─────────────────────────────────────────────────────────────
    # Métricas de pagos (tabla: public.payments)
    # ─────────────────────────────────────────────────────────────

    async def get_paying_users_total(self) -> int:
        """
        Cuenta usuarios distintos con al menos 1 pago exitoso.
        Tabla: public.payments
        Columna: status (payment_status_enum)
        Status exitoso: 'succeeded'
        
        Maneja gracefully si la tabla de pagos no existe.
        
        SIEMPRE retorna int (nunca None).
        """
        try:
            q = text("""
                SELECT COUNT(DISTINCT user_id) 
                FROM public.payments 
                WHERE status = 'succeeded'
            """)
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.debug("get_paying_users_total failed: %s", e)
        return 0

    # ─────────────────────────────────────────────────────────────
    # Helpers legacy
    # ─────────────────────────────────────────────────────────────

    async def get_login_attempts_hourly(self, p_from, p_to):
        """
        Devuelve lista de intentos de login por hora (para dashboards).
        """
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
