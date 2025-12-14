
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/db/snapshot.py

Snapshot consolidado (desde BD) combinando pagos, créditos, reembolsos,
distribución de saldos y (opcional) conciliación.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .base import coerce_dt, date_floor, date_ceil
from .payments import get_payments_daily, get_payments_kpis
from .credits import get_credits_daily, get_credits_kpis
from .refunds import get_refunds_daily, get_refunds_kpis
from .balance import get_balance_distribution
from .reconciliation import get_reconciliation_last_runs


async def get_metrics_snapshot_from_db(
    db: AsyncSession,
    since,
    until,
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """Snapshot consolidado consultando vistas/MVs."""
    s = coerce_dt(since)
    u = coerce_dt(until)

    payments_series = await get_payments_daily(db, s, u, provider, currency)
    payments_kpis = await get_payments_kpis(db, s, u, provider, currency)

    credits_series = await get_credits_daily(db, s, u, provider, currency)
    credits_kpis = await get_credits_kpis(db, s, u, provider, currency)

    refunds_series = await get_refunds_daily(db, s, u, provider, currency)
    refunds_kpis = await get_refunds_kpis(db, s, u, provider, currency)

    balance = await get_balance_distribution(db)

    try:
        reconciliation = await get_reconciliation_last_runs(db, limit=20)
    except Exception:
        reconciliation = []

    return {
        "range": {"since": date_floor(s).isoformat(), "until": date_ceil(u).isoformat()},
        "filters": {"provider": provider, "currency": currency},
        "payments": {"series": payments_series, "kpis": payments_kpis},
        "credits": {"series": credits_series, "kpis": credits_kpis},
        "refunds": {"series": refunds_series, "kpis": refunds_kpis},
        "balance": balance,
        "reconciliation": reconciliation,
    }

# Fin del archivo backend\app\modules\payments\metrics\aggregators\db\snapshot.py