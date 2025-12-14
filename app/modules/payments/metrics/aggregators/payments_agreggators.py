
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/payments_aggregators.py

Aggregators para métricas históricas del módulo de pagos.
Consulta vistas / materialized views de KPIs (PostgreSQL) y devuelve
estructuras JSON listas para consumo por el módulo Administración.

Vistas/MVs esperadas (nombres sugeridos):
- mv_kpi_payments_daily        -- pagos por día (success rate, montos, latencia)
- mv_kpi_credits_daily         -- créditos vendidos/consumidos/delta por día
- mv_kpi_refunds_daily         -- reembolsos por día (monto, tasa)
- kpi_user_balance_distribution -- percentiles de saldo y conteo de usuarios
- (opcional) kpi_reconciliation_last_runs -- estado de conciliaciones

El agregador es tolerante a cambios de columnas: usa Result.mappings() y
no fuerza esquemas rígidos (si alguna columna no existe, simplemente no aparece
en el resultado).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_dt(dt: Optional[datetime]) -> datetime:
    """Asegura datetime con tz UTC."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _date_floor(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _date_ceil(dt: datetime) -> datetime:
    return (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


async def _fetch_rows(db: AsyncSession, sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ejecuta una consulta y devuelve una lista de dicts (mappings)."""
    res = await db.execute(text(sql), params)
    return [dict(row) for row in res.mappings().all()]


# ---------------------------------------------------------------------------
# Payments (diario)
# ---------------------------------------------------------------------------

async def get_payments_daily(
    db: AsyncSession,
    since: Optional[datetime],
    until: Optional[datetime],
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve series diarias de pagos (por rango y filtros opcionales).
    Columnas esperadas (flexible): day, provider, currency, payments_total,
    payments_succeeded, success_rate, amount_cents_succeeded, avg_latency_ms, p95_ms, p99_ms.
    """
    s = _date_floor(_coerce_dt(since))
    u = _date_ceil(_coerce_dt(until))
    sql = """
        SELECT *
        FROM mv_kpi_payments_daily
        WHERE (:provider IS NULL OR provider = :provider)
          AND (:currency IS NULL OR currency = :currency)
          AND day >= :since::date AND day < :until::date
        ORDER BY day ASC, provider, currency
    """
    return await _fetch_rows(
        db,
        sql,
        {"since": s.date().isoformat(), "until": u.date().isoformat(), "provider": provider, "currency": currency},
    )


async def get_payments_kpis(
    db: AsyncSession,
    since: Optional[datetime],
    until: Optional[datetime],
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """
    KPIs agregados a partir de la vista diaria (sumatorias/tasas sobre el rango).
    Retorna: total, succeeded, failed (= total - succeeded), success_rate, amount_cents_succeeded.
    Si existen columnas de latencia (avg_ms/p95/p99) se devuelve el promedio simple del rango.
    """
    rows = await get_payments_daily(db, since, until, provider, currency)

    total = sum(int(r.get("payments_total", 0) or 0) for r in rows)
    succeeded = sum(int(r.get("payments_succeeded", 0) or 0) for r in rows)
    failed = max(total - succeeded, 0)
    amount_cents_succeeded = sum(int(r.get("amount_cents_succeeded", 0) or 0) for r in rows)

    # Latencias (si están disponibles)
    avg_list = [float(r.get("avg_latency_ms")) for r in rows if r.get("avg_latency_ms") is not None]
    p95_list = [float(r.get("p95_ms")) for r in rows if r.get("p95_ms") is not None]
    p99_list = [float(r.get("p99_ms")) for r in rows if r.get("p99_ms") is not None]

    def avg_safe(lst: List[float]) -> float:
        return (sum(lst) / len(lst)) if lst else 0.0

    return {
        "range": {"since": _date_floor(_coerce_dt(since)).isoformat(), "until": _date_ceil(_coerce_dt(until)).isoformat()},
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


# ---------------------------------------------------------------------------
# Credits (diario)
# ---------------------------------------------------------------------------

async def get_credits_daily(
    db: AsyncSession,
    since: Optional[datetime],
    until: Optional[datetime],
    provider: Optional[str] = None,   # por si tu MV separa por provider
    currency: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve series diarias de créditos vendidos/consumidos/delta.
    Columnas esperadas (flexible): day, credits_sold, credits_consumed, credits_delta, provider?, currency?
    """
    s = _date_floor(_coerce_dt(since))
    u = _date_ceil(_coerce_dt(until))
    # Soporta vistas con o sin provider/currency (los filtros se ignoran si no existen)
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
    return await _fetch_rows(
        db,
        sql,
        {"since": s.date().isoformat(), "until": u.date().isoformat(), "provider": provider, "currency": currency},
    )


async def get_credits_kpis(
    db: AsyncSession,
    since: Optional[datetime],
    until: Optional[datetime],
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """
    KPIs agregados de créditos en el rango.
    Retorna: sold, consumed, delta_total.
    """
    rows = await get_credits_daily(db, since, until, provider, currency)
    sold = sum(float(r.get("credits_sold", 0) or 0) for r in rows)
    consumed = sum(float(r.get("credits_consumed", 0) or 0) for r in rows)
    delta_total = sum(float(r.get("credits_delta", 0) or 0) for r in rows)

    return {
        "range": {"since": _date_floor(_coerce_dt(since)).isoformat(), "until": _date_ceil(_coerce_dt(until)).isoformat()},
        "filters": {"provider": provider, "currency": currency},
        "credits_sold": sold,
        "credits_consumed": consumed,
        "credits_delta_total": delta_total,
    }


# ---------------------------------------------------------------------------
# Refunds (diario)
# ---------------------------------------------------------------------------

async def get_refunds_daily(
    db: AsyncSession,
    since: Optional[datetime],
    until: Optional[datetime],
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve series diarias de reembolsos (monto y conteos).
    Columnas esperadas (flexible): day, provider, currency, refunds_count, refunds_amount_cents, refund_rate
    """
    s = _date_floor(_coerce_dt(since))
    u = _date_ceil(_coerce_dt(until))
    sql = """
        SELECT *
        FROM mv_kpi_refunds_daily
        WHERE (:provider IS NULL OR provider = :provider)
          AND (:currency IS NULL OR currency = :currency)
          AND day >= :since::date AND day < :until::date
        ORDER BY day ASC, provider, currency
    """
    return await _fetch_rows(
        db,
        sql,
        {"since": s.date().isoformat(), "until": u.date().isoformat(), "provider": provider, "currency": currency},
    )


async def get_refunds_kpis(
    db: AsyncSession,
    since: Optional[datetime],
    until: Optional[datetime],
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """
    KPIs agregados de reembolsos en el rango.
    Retorna: refunds_count, refunds_amount_cents, refund_rate (si es posible).
    """
    rows = await get_refunds_daily(db, since, until, provider, currency)

    refunds_count = sum(int(r.get("refunds_count", 0) or 0) for r in rows)
    refunds_amount_cents = sum(int(r.get("refunds_amount_cents", 0) or 0) for r in rows)

    # refund_rate diaria puede existir como columna; si no, calculamos ratio simple si hay pagos
    # (en general, refund_rate a nivel rango es discutible; devolvemos promedio simple si existe)
    refund_rate_list = [float(r.get("refund_rate")) for r in rows if r.get("refund_rate") is not None]
    refund_rate_avg = (sum(refund_rate_list) / len(refund_rate_list)) if refund_rate_list else 0.0

    return {
        "range": {"since": _date_floor(_coerce_dt(since)).isoformat(), "until": _date_ceil(_coerce_dt(until)).isoformat()},
        "filters": {"provider": provider, "currency": currency},
        "refunds_count": refunds_count,
        "refunds_amount_cents": refunds_amount_cents,
        "refund_rate_avg": refund_rate_avg,
    }


# ---------------------------------------------------------------------------
# Balance percentiles (snapshot)
# ---------------------------------------------------------------------------

async def get_balance_distribution(db: AsyncSession) -> Dict[str, Any]:
    """
    Devuelve percentiles de saldo disponibles (si existe la vista kpi_user_balance_distribution).
    Columnas esperadas: p10, p25, p50, p75, p90, users_count, currency? (opcional)
    """
    sql = """
        SELECT *
        FROM kpi_user_balance_distribution
        LIMIT 100
    """
    rows = await _fetch_rows(db, sql, {})
    # Si hay múltiples monedas/registros, devolvemos tal cual la lista para que el frontend decida.
    return {"entries": rows}


# ---------------------------------------------------------------------------
# Reconciliación (opcional)
# ---------------------------------------------------------------------------

async def get_reconciliation_last_runs(db: AsyncSession, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Devuelve las últimas corridas de conciliación si existe la vista/tabla kpi_reconciliation_last_runs.
    Columnas sugeridas: run_at, provider, discrepancies_missing_in_db, discrepancies_missing_in_provider,
                        amount_mismatch, status_mismatch, notes
    """
    sql = """
        SELECT *
        FROM kpi_reconciliation_last_runs
        ORDER BY run_at DESC
        LIMIT :limit
    """
    return await _fetch_rows(db, sql, {"limit": int(limit)})


# ---------------------------------------------------------------------------
# Snapshot integrado (útil para /payments/metrics/snapshot si se desea BD)
# ---------------------------------------------------------------------------

async def get_metrics_snapshot_from_db(
    db: AsyncSession,
    since: Optional[datetime],
    until: Optional[datetime],
    provider: Optional[str] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Devuelve un snapshot consolidado consultando MVs/vistas:
    - payments.daily (series + KPIs)
    - credits.daily (series + KPIs)
    - refunds.daily (series + KPIs)
    - balance.percentiles
    - reconciliation.last_runs (opcional)
    """
    s = _coerce_dt(since)
    u = _coerce_dt(until)

    payments_series = await get_payments_daily(db, s, u, provider, currency)
    payments_kpis = await get_payments_kpis(db, s, u, provider, currency)

    credits_series = await get_credits_daily(db, s, u, provider, currency)
    credits_kpis = await get_credits_kpis(db, s, u, provider, currency)

    refunds_series = await get_refunds_daily(db, s, u, provider, currency)
    refunds_kpis = await get_refunds_kpis(db, s, u, provider, currency)

    balance = await get_balance_distribution(db)

    # reconciliación es opcional; si la vista no existe, dejamos lista vacía
    try:
        reconciliation = await get_reconciliation_last_runs(db, limit=20)
    except Exception:
        reconciliation = []

    return {
        "range": {"since": _date_floor(s).isoformat(), "until": _date_ceil(u).isoformat()},
        "filters": {"provider": provider, "currency": currency},
        "payments": {"series": payments_series, "kpis": payments_kpis},
        "credits": {"series": credits_series, "kpis": credits_kpis},
        "refunds": {"series": refunds_series, "kpis": refunds_kpis},
        "balance": balance,
        "reconciliation": reconciliation,
    }

# Fin del archivo backend\app\modules\payments\metrics\aggregators\payments_agreggators.py