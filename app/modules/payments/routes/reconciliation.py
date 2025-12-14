
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/reconciliation.py

Rutas para reconciliación de pagos con proveedores.

Endpoint:
- GET /payments/reconciliation/report

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.payments.enums import PaymentProvider
from app.modules.payments.facades.reconciliation import generate_reconciliation_report

router = APIRouter(
    prefix="/reconciliation",
    tags=["payments:reconciliation"],
)


@router.get("/report", response_model=Dict[str, Any])
async def reconciliation_report(
    provider: PaymentProvider = Query(..., description="Proveedor a reconciliar."),
    start_date: datetime = Query(..., description="Fecha/hora de inicio del período."),
    end_date: datetime = Query(..., description="Fecha/hora de fin del período."),
    include_matched: bool = Query(
        False,
        description="Incluir o no la lista completa de pagos reconciliados.",
    ),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Genera un reporte de reconciliación para un proveedor y período dado.
    Pensado para uso administrativo / monitoreo.
    """
    try:
        report = await generate_reconciliation_report(
            session,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            include_matched=include_matched,
        )
        return report
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# Fin del archivo backend/app/modules/payments/routes/reconciliation.py