
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/db/__init__.py

Re-exporta funciones de agregadores DB para imports limpios.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from .base import coerce_dt, date_floor, date_ceil, fetch_rows
from .payments import get_payments_daily, get_payments_kpis
from .credits import get_credits_daily, get_credits_kpis
from .refunds import get_refunds_daily, get_refunds_kpis
from .balance import get_balance_distribution
from .reconciliation import get_reconciliation_last_runs
from .snapshot import get_metrics_snapshot_from_db

__all__ = [
    "coerce_dt",
    "date_floor",
    "date_ceil",
    "fetch_rows",
    "get_payments_daily",
    "get_payments_kpis",
    "get_credits_daily",
    "get_credits_kpis",
    "get_refunds_daily",
    "get_refunds_kpis",
    "get_balance_distribution",
    "get_reconciliation_last_runs",
    "get_metrics_snapshot_from_db",
]

# Fin del archivo backend\app\modules\payments\metrics\aggregators\db\__init__.py