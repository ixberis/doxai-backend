
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/db/reconciliation.py

Consultas de corridas recientes de conciliación (opcional).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from .base import fetch_rows


async def get_reconciliation_last_runs(db: AsyncSession, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Devuelve últimas corridas si existe la vista/tabla kpi_reconciliation_last_runs.
    Columnas sugeridas: run_at, provider, discrepancies_missing_in_db, discrepancies_missing_in_provider,
                        amount_mismatch, status_mismatch, notes
    """
    sql = """
        SELECT *
        FROM kpi_reconciliation_last_runs
        ORDER BY run_at DESC
        LIMIT :limit
    """
    return await fetch_rows(db, sql, {"limit": int(limit)})

# Fin del archivo backend\app\modules\payments\metrics\aggregators\db\reconciliation.py