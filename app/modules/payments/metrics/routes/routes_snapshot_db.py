
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/routes/routes_snapshot_db.py

Rutas de snapshot DESDE BD (MVs/Vistas) para el módulo de pagos:
- /payments/metrics/snapshot-db  → Snapshot JSON (vistas/MVs en PostgreSQL)

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Depends
from starlette.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..aggregators.db import get_metrics_snapshot_from_db
from app.shared.database import get_db

# Importar dependencia de autenticación
try:
    from app.modules.auth.dependencies import get_current_user_admin
except ImportError:  # pragma: no cover - modo tests / sin módulo auth
    # Stub permisivo para entornos sin módulo auth: simula un admin.
    async def get_current_user_admin():
        """Stub usado cuando el módulo de autenticación no está disponible.

        En producción, se usará la implementación real de auth.dependencies.
        Aquí devolvemos un objeto simple que representa un usuario admin
        para permitir pruebas de métricas sin configurar auth.
        """

        class _AdminUser:
            id = 1
            is_admin = True

        return _AdminUser()

router_snapshot_db = APIRouter(tags=["payments-metrics"])


@router_snapshot_db.get("/metrics/snapshot-db")
async def snapshot_db(
    hours: int = Query(24, ge=1, le=168, description="Ventana de tiempo en horas (hasta 7 días)"),
    provider: Optional[str] = Query(None, description="Filtrar métricas por proveedor"),
    currency: Optional[str] = Query(None, description="Filtrar métricas por moneda"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user_admin),
) -> JSONResponse:
    """
    Snapshot consolidado desde la base de datos (vistas/MVs).
    Útil para paneles históricos y auditoría sin exponer PII.
    """
    until = datetime.now(timezone.utc)
    since = until - timedelta(hours=hours)

    snapshot = await get_metrics_snapshot_from_db(
        db=db,
        since=since,
        until=until,
        provider=provider,
        currency=currency,
    )

    payload: Dict[str, Any] = {
        "source": "database",
        "range": {"since": since.isoformat(), "until": until.isoformat(), "hours": hours},
        "filters": {"provider": provider, "currency": currency},
        "snapshot": snapshot,
    }
    return JSONResponse(content=payload)

# Fin del archivo backend\app\modules\payments\metrics\routes\routes_snapshot_db.py