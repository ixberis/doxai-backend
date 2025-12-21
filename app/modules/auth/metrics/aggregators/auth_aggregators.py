
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
Actualizado: 2025-12-21 - Alineado con esquema real
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA REAL (EVIDENCIA)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Tabla: public.app_users
#   - user_id (PK, int)
#   - user_is_activated (bool) ← campo real de activación
#   - user_activated_at (timestamp, nullable)
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
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─────────────────────────────────────────────────────────────
    # Métricas de usuarios (tabla: public.app_users)
    # ─────────────────────────────────────────────────────────────

    async def get_users_total(self) -> Optional[int]:
        """
        Cuenta total de usuarios registrados.
        Tabla: public.app_users
        """
        q = text("SELECT COUNT(*) FROM public.app_users")
        res = await self.db.execute(q)
        row = res.first()
        if row and row[0] is not None:
            return int(row[0])
        return None

    async def get_users_activated_total(self) -> Optional[int]:
        """
        Cuenta usuarios con cuenta activada.
        Tabla: public.app_users
        Columna: user_is_activated (bool)
        """
        q = text("""
            SELECT COUNT(*) FROM public.app_users 
            WHERE user_is_activated = true
        """)
        res = await self.db.execute(q)
        row = res.first()
        if row and row[0] is not None:
            return int(row[0])
        return None

    # ─────────────────────────────────────────────────────────────
    # Métricas de sesiones (tabla: public.user_sessions)
    # ─────────────────────────────────────────────────────────────

    async def get_active_sessions(self) -> Optional[int]:
        """
        Cuenta sesiones activas (no revocadas, no expiradas).
        Tabla: public.user_sessions
        Condición: revoked_at IS NULL AND expires_at > NOW()
        
        Intenta usar función SECURITY DEFINER si existe, 
        fallback a query directa.
        """
        # Intentar función SECURITY DEFINER primero
        try:
            q = text("SELECT public.f_auth_active_sessions_count()")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                return int(row[0])
        except Exception:
            pass  # Fallback a query directa
        
        # Query directa como fallback
        q = text("""
            SELECT COUNT(*) 
            FROM public.user_sessions 
            WHERE revoked_at IS NULL 
              AND expires_at > NOW()
        """)
        res = await self.db.execute(q)
        row = res.first()
        if row and row[0] is not None:
            return int(row[0])
        return None

    async def get_active_users_total(self) -> Optional[int]:
        """
        Cuenta usuarios distintos con sesión activa.
        Tabla: public.user_sessions
        Condición: revoked_at IS NULL AND expires_at > NOW()
        """
        q = text("""
            SELECT COUNT(DISTINCT user_id) 
            FROM public.user_sessions 
            WHERE revoked_at IS NULL 
              AND expires_at > NOW()
        """)
        res = await self.db.execute(q)
        row = res.first()
        if row and row[0] is not None:
            return int(row[0])
        return None

    # ─────────────────────────────────────────────────────────────
    # Métricas de conversión
    # ─────────────────────────────────────────────────────────────

    async def get_latest_activation_conversion_ratio(self) -> Optional[float]:
        """
        Obtiene el ratio más reciente de conversión registro→activación.
        Intenta usar función SECURITY DEFINER si existe.
        Returns ratio (0-1), not percentage. Frontend multiplies by 100.
        """
        try:
            q = text("SELECT public.f_auth_activation_rate_latest()")
            res = await self.db.execute(q)
            row = res.first()
            if row and row[0] is not None:
                # SQL returns percentage (e.g., 11.11), convert to ratio (0.1111)
                return float(row[0]) / 100.0
        except Exception:
            pass  # Fallback calculado en el endpoint
        return None

    async def get_activation_conversion_ratio(self) -> Optional[float]:
        """
        Calcula ratio de conversión: users_activated / users_total.
        Fallback si la función SQL no existe.
        """
        users_total = await self.get_users_total()
        users_activated = await self.get_users_activated_total()
        
        if users_total and users_total > 0 and users_activated is not None:
            return users_activated / users_total
        return None

    # ─────────────────────────────────────────────────────────────
    # Métricas de pagos (tabla: public.payments)
    # ─────────────────────────────────────────────────────────────

    async def get_paying_users_total(self) -> Optional[int]:
        """
        Cuenta usuarios distintos con al menos 1 pago exitoso.
        Tabla: public.payments
        Columna: status (payment_status_enum)
        Status exitoso: 'succeeded'
        
        Maneja gracefully si la tabla de pagos no existe.
        """
        q = text("""
            SELECT COUNT(DISTINCT user_id) 
            FROM public.payments 
            WHERE status = 'succeeded'
        """)
        res = await self.db.execute(q)
        row = res.first()
        if row and row[0] is not None:
            return int(row[0])
        return None

    # ─────────────────────────────────────────────────────────────
    # Helpers legacy
    # ─────────────────────────────────────────────────────────────

    async def get_login_attempts_hourly(self, p_from, p_to):
        """
        Devuelve lista de intentos de login por hora (para dashboards).
        """
        q = text("""
            SELECT ts_hour, success, reason, attempts
            FROM f_auth_login_attempts_hourly(:p_from, :p_to)
        """)
        res = await self.db.execute(q, {"p_from": p_from, "p_to": p_to})
        return res.fetchall()


# Fin del archivo backend/app/modules/auth/metrics/aggregators/auth_aggregators.py
