
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/aggregators/auth_aggregators.py

Agregadores SQL para métricas del módulo Auth.

Consulta las vistas agregadas definidas en la base de datos
(v_auth_active_sessions, v_auth_activation_conversion_daily, etc.)
y devuelve resultados seguros sin PII.

Autor: Ixchel Beristain
Fecha: 2025-11-07
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class AuthAggregators:
    """
    Lógica de lectura/agregado desde vistas SQL.
    Estos métodos devuelven valores crudos que pueden
    ser usados por exportadores o dashboards internos.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_sessions(self) -> int:
        """Cuenta sesiones activas (no revocadas y no expiradas)."""
        q = text("SELECT active_sessions FROM v_auth_active_sessions")
        res = await self.db.execute(q)
        row = res.first()
        return int(row[0] or 0) if row else 0

    async def get_latest_activation_conversion_ratio(self) -> float:
        """Obtiene el ratio más reciente de conversión registro→activación."""
        q = text("""
            SELECT conversion_ratio
            FROM v_auth_activation_conversion_daily
            ORDER BY day DESC
            LIMIT 1
        """)
        res = await self.db.execute(q)
        row = res.first()
        return float(row[0]) if row and row[0] is not None else 0.0

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
