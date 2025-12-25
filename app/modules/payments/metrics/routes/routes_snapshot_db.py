
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

from fastapi import APIRouter, Query, Depends, HTTPException, status
from starlette.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..aggregators import db as aggregators_db
from app.shared.database import get_db

# Importar dependencia de autenticación admin
try:
    from app.modules.auth.dependencies import require_admin as get_current_user_admin
except ImportError:  # pragma: no cover - modo tests / sin módulo auth
    # Fallback para tests sin módulo auth completo
    async def get_current_user_admin() -> str:
        """
        Stub de autenticación admin para entornos sin módulo auth.
        
        Raises:
            HTTPException 401: Siempre, porque no hay auth configurada.
        """
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "auth_not_configured",
                "message": "Authentication module not available",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

router_snapshot_db = APIRouter(tags=["payments-metrics"])


@router_snapshot_db.get("/metrics/snapshot-db")
async def snapshot_db(
    hours: int = Query(24, ge=1, le=168, description="Ventana de tiempo en horas (hasta 7 días)"),
    provider: Optional[str] = Query(None, description="Filtrar métricas por proveedor"),
    currency: Optional[str] = Query(None, description="Filtrar métricas por moneda"),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user_admin),
) -> JSONResponse:
    """
    Snapshot consolidado desde la base de datos (vistas/MVs).
    Útil para paneles históricos y auditoría sin exponer PII.
    """
    until = datetime.now(timezone.utc)
    since = until - timedelta(hours=hours)

    snapshot = await aggregators_db.get_metrics_snapshot_from_db(
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
