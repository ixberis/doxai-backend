
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/db/refunds.py

Consultas de reembolsos (series diarias + KPIs).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .base import coerce_dt, date_floor, date_ceil, fetch_rows


async def get_refunds_daily(
    db: AsyncSession,
    since,
    until,
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Series diarias de reembolsos.
    Columnas: day, provider, currency, refunds_count, refunds_amount_cents, refund_rate (opcional).
    """
    s = date_floor(coerce_dt(since))
    u = date_ceil(coerce_dt(until))
    sql = """
        SELECT *
        FROM mv_kpi_refunds_daily
        WHERE (:provider IS NULL OR provider = :provider)
          AND (:currency IS NULL OR currency = :currency)
          AND day >= :since::date AND day < :until::date
        ORDER BY day ASC, provider, currency
    """
    return await fetch_rows(
        db,
        sql,
        {"since": s.date().isoformat(), "until": u.date().isoformat(), "provider": provider, "currency": currency},
    )


async def get_refunds_kpis(
    db: AsyncSession,
    since,
    until,
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """KPIs agregados de reembolsos del rango."""
    rows = await get_refunds_daily(db, since, until, provider, currency)
    refunds_count = sum(int(r.get("refunds_count", 0) or 0) for r in rows)
    refunds_amount_cents = sum(int(r.get("refunds_amount_cents", 0) or 0) for r in rows)

    refund_rate_list = [float(r.get("refund_rate")) for r in rows if r.get("refund_rate") is not None]
    refund_rate_avg = (sum(refund_rate_list) / len(refund_rate_list)) if refund_rate_list else 0.0

    return {
        "range": {"since": date_floor(coerce_dt(since)).isoformat(), "until": date_ceil(coerce_dt(until)).isoformat()},
        "filters": {"provider": provider, "currency": currency},
        "refunds_count": refunds_count,
        "refunds_amount_cents": refunds_amount_cents,
        "refund_rate_avg": refund_rate_avg,
    }
# Fin del archivo backend\app\modules\payments\metrics\aggregators\db\refunds.py