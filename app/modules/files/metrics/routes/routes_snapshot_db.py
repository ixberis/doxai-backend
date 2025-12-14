
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/routes/routes_snapshot_db.py

Snapshot DB de métricas del módulo Files.

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..aggregators.db.snapshot import FilesMetricsAggregator
from ..aggregators.storage.time_window import clamp_days

# Dependencia de DB (ajusta si tu proyecto usa otra ruta)
try:
    from app.shared.database.database import get_db  # FastAPI Depends
except Exception:  # pragma: no cover
    async def get_db():  # type: ignore
        raise HTTPException(status_code=500, detail="DB dependency not available")


router = APIRouter(tags=["files:metrics"])


@router.get("/db")
async def files_metrics_snapshot_db(
    project_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Devuelve un snapshot JSON basado en consultas a la DB.
    """
    agg = FilesMetricsAggregator()
    snap = await agg.build_snapshot(db, project_id=project_id, days=clamp_days(days))
    return snap


# Fin del archivo backend/app/modules/files/metrics/routes/routes_snapshot_db.py
