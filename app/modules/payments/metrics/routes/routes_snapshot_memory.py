
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/routes/routes_snapshot_memory.py

Rutas de snapshot EN MEMORIA para el módulo de pagos:
- /payments/metrics/snapshot     → Snapshot JSON (collector en memoria)

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, Query, Depends
from starlette.responses import JSONResponse

from ..collectors.metrics_collector import get_metrics_collector

# Importar dependencia de autenticación
try:
    from app.modules.auth.dependencies import get_current_user_admin
except ImportError:
    # Definir stub que será sobrescrito por dependency_overrides en tests
    async def get_current_user_admin():
        """Stub - será sobrescrito en tests vía dependency_overrides."""
        raise RuntimeError("get_current_user_admin not configured")

router_snapshot_memory = APIRouter(tags=["payments-metrics"])


@router_snapshot_memory.get("/metrics/snapshot")
async def snapshot(
    hours: int = Query(1, ge=1, le=24, description="Ventana de tiempo en horas"),
    endpoint: Optional[str] = Query(None, description="Filtrar métricas por endpoint"),
    provider: Optional[str] = Query(None, description="Filtrar métricas por proveedor"),
    current_user: Any = Depends(get_current_user_admin),
) -> JSONResponse:
    """
    Snapshot JSON para el módulo de Administración (sin PII).
    Usa el collector en memoria (últimas horas).
    """
    collector = get_metrics_collector()

    endpoints = collector.get_endpoint_metrics(endpoint=endpoint, hours=hours)
    providers = collector.get_provider_conversions(provider=provider, hours=hours)
    summary = collector.get_summary()
    health = collector.get_health_status()

    data: Dict[str, Any] = {
        "success": True,
        "snapshot": {
            "source": "memory",
            "time_window_hours": hours,
            "filters": {"endpoint": endpoint, "provider": provider},
            "endpoints": endpoints,
            "providers": providers,
            "summary": summary,
            "health": {
                "status": health.get("status"),
                "alerts": health.get("alerts", []),
                "timestamp": health.get("timestamp"),
            },
        },
    }
    return JSONResponse(content=data)

# Fin del archivo backend\app\modules\payments\metrics\routes\routes_snapshot_memory.py