
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/db/payments.py

Consultas de pagos (series diarias + KPIs agregados).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .base import coerce_dt, date_floor, date_ceil, fetch_rows


async def get_payments_daily(
    db: AsyncSession,
    since,
    until,
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve series diarias de pagos.
    Columnas esperadas (flexible): day, provider, currency, payments_total,
    payments_succeeded, success_rate, amount_cents_succeeded, avg_latency_ms, p95_ms, p99_ms.
    """
    s = date_floor(coerce_dt(since))
    u = date_ceil(coerce_dt(until))
    sql = """
        SELECT *
        FROM mv_kpi_payments_daily
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


async def get_payments_kpis(
    db: AsyncSession,
    since,
    until,
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """
    KPIs agregados del rango: total, succeeded, failed, success_rate,
    amount_cents_succeeded y (si existen) latencias promedio del rango.
    """
    rows = await get_payments_daily(db, since, until, provider, currency)

    total = sum(int(r.get("payments_total", 0) or 0) for r in rows)
    succeeded = sum(int(r.get("payments_succeeded", 0) or 0) for r in rows)
    failed = max(total - succeeded, 0)
    amount_cents_succeeded = sum(int(r.get("amount_cents_succeeded", 0) or 0) for r in rows)

    avg_list = [float(r.get("avg_latency_ms")) for r in rows if r.get("avg_latency_ms") is not None]
    p95_list = [float(r.get("p95_ms")) for r in rows if r.get("p95_ms") is not None]
    p99_list = [float(r.get("p99_ms")) for r in rows if r.get("p99_ms") is not None]

    def avg_safe(xs):
        return (sum(xs) / len(xs)) if xs else 0.0

    return {
        "range": {"since": date_floor(coerce_dt(since)).isoformat(), "until": date_ceil(coerce_dt(until)).isoformat()},
        "filters": {"provider": provider, "currency": currency},
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": (succeeded / total * 100.0) if total else 0.0,
        "amount_cents_succeeded": amount_cents_succeeded,
        "latency": {
            "avg_ms": avg_safe(avg_list),
            "p95_ms": avg_safe(p95_list),
            "p99_ms": avg_safe(p99_list),
        },
    }
 #Fin del archivo backend\app\modules\payments\metrics\aggregators\db\payments.py