
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/db/balance.py

Consultas de distribución de saldos (percentiles).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from .base import fetch_rows


async def get_balance_distribution(db: AsyncSession) -> Dict[str, Any]:
    """
    Devuelve percentiles de saldo disponibles (si existe la vista kpi_user_balance_distribution).
    Columnas esperadas: p10, p25, p50, p75, p90, users_count, currency? (opcional)
    """
    sql = "SELECT * FROM kpi_user_balance_distribution LIMIT 100"
    rows: List[Dict[str, Any]] = await fetch_rows(db, sql, {})
    return {"entries": rows}
# Fin del archivo backend\app\modules\payments\metrics\aggregators\db\balance.py