
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/db/credits.py

Consultas de créditos (series diarias + KPIs).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .base import coerce_dt, date_floor, date_ceil, fetch_rows


async def get_credits_daily(
    db: AsyncSession,
    since,
    until,
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Series diarias de créditos vendidos/consumidos/delta.
    Columnas: day, credits_sold, credits_consumed, credits_delta (provider/currency opcionales).
    """
    s = date_floor(coerce_dt(since))
    u = date_ceil(coerce_dt(until))
    sql = """
        SELECT *
        FROM mv_kpi_credits_daily
        WHERE (NOT EXISTS(
                 SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'mv_kpi_credits_daily' AND column_name = 'provider'
              ) OR :provider IS NULL OR provider = :provider)
          AND (NOT EXISTS(
                 SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'mv_kpi_credits_daily' AND column_name = 'currency'
              ) OR :currency IS NULL OR currency = :currency)
          AND day >= :since::date AND day < :until::date
        ORDER BY day ASC
    """
    return await fetch_rows(
        db,
        sql,
        {"since": s.date().isoformat(), "until": u.date().isoformat(), "provider": provider, "currency": currency},
    )


async def get_credits_kpis(
    db: AsyncSession,
    since,
    until,
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """KPIs agregados del rango de créditos."""
    rows = await get_credits_daily(db, since, until, provider, currency)
    sold = sum(float(r.get("credits_sold", 0) or 0) for r in rows)
    consumed = sum(float(r.get("credits_consumed", 0) or 0) for r in rows)
    delta_total = sum(float(r.get("credits_delta", 0) or 0) for r in rows)

    return {
        "range": {"since": date_floor(coerce_dt(since)).isoformat(), "until": date_ceil(coerce_dt(until)).isoformat()},
        "filters": {"provider": provider, "currency": currency},
        "credits_sold": sold,
        "credits_consumed": consumed,
        "credits_delta_total": delta_total,
    }
# Fin del archivo backend\app\modules\payments\metrics\aggregators\db\credits.py