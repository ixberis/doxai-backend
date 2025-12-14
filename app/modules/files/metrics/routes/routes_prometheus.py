# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/routes/routes_prometheus.py

Endpoint de exportación en formato Prometheus para el módulo Files.

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..aggregators.db.snapshot import FilesMetricsAggregator
from ..aggregators.storage.time_window import clamp_days
from ..exporters.prometheus_exporter import snapshot_to_prometheus_text

# Dependencia de DB (ajusta si tu proyecto usa otra ruta)
try:
    from app.shared.database.database import get_db  # FastAPI Depends
except Exception:  # pragma: no cover
    async def get_db():  # type: ignore
        raise HTTPException(status_code=500, detail="DB dependency not available")


router = APIRouter(tags=["files:metrics"])


@router.get("/prometheus", response_class=Response)
async def files_metrics_prometheus(
    project_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Exporta el snapshot en texto plano para Prometheus.
    """
    agg = FilesMetricsAggregator()
    snap = await agg.build_snapshot(db, project_id=project_id, days=clamp_days(days))
    text = snapshot_to_prometheus_text(snap)
    return Response(content=text, media_type="text/plain; version=0.0.4; charset=utf-8")


# Fin del archivo backend/app/modules/files/metrics/routes/routes_prometheus.py
