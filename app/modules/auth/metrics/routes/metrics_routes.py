
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/metrics_routes.py

Ruteador interno de métricas del módulo Auth.

Expone endpoints JSON de monitoreo interno:
- /_internal/auth/metrics/snapshot: refresca gauges derivados
  y devuelve un resumen de métricas seguras (sin PII).

Autor: Ixchel Beristain
Fecha: 2025-11-07
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.metrics.schemas.metrics_schemas import AuthMetricsSnapshot
from app.modules.auth.metrics.exporters.prometheus_exporter import AuthPrometheusExporter

router = APIRouter(prefix="/_internal/auth/metrics", tags=["metrics-auth"])


@router.get("/snapshot", response_model=AuthMetricsSnapshot)
async def get_auth_metrics_snapshot(db: AsyncSession = Depends(get_db)):
    """
    Refresca gauges derivados y devuelve un snapshot JSON
    con métricas agregadas (seguras) para dashboard interno.
    """
    exp = AuthPrometheusExporter(db)
    data = await exp.refresh_gauges()
    return AuthMetricsSnapshot(
        active_sessions=data["active_sessions"],
        activation_conversion_ratio=data["activation_conversion_ratio"],
    )


# Fin del archivo backend/app/modules/auth/metrics/routes/metrics_routes.py
