
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/payments.py

Rutas genéricas de pagos.

Endpoints:
- GET /payments/intents/{payment_id}
- GET /payments/{payment_id}/status (FASE 2)

Autor: Ixchel Beristain
Fecha: 2025-11-21 (actualizado 2025-12-13)
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.payments.repositories import PaymentRepository
from app.modules.payments.facades.payments import (
    get_payment_intent,
    get_payment_status,
    PaymentIntentNotFound,
)
from app.modules.payments.schemas.payment_status_schemas import PaymentStatusResponse

router = APIRouter(
    prefix="",
    tags=["payments"],
)


@router.get(
    "/intents/{payment_id}",
    response_model=Dict[str, Any],
)
async def get_payment_intent_route(
    payment_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Obtiene información básica y estado de un pago (intent).
    """
    payment_repo = PaymentRepository()
    try:
        data = await get_payment_intent(
            session,
            payment_id=payment_id,
            payment_repo=payment_repo,
        )
        return data
    except PaymentIntentNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/{payment_id}/status",
    response_model=PaymentStatusResponse,
    summary="Estado de pago para polling",
    description="""
    FASE 2: Endpoint de estado de pago para polling del Frontend.
    
    El Frontend puede:
    - Hacer polling hasta que is_final=True
    - Mostrar "Procesando pago..." cuando is_final=False
    - Usar retry_after_seconds para determinar intervalo de polling
    
    Nunca acredita créditos ni expone datos sensibles.
    """,
)
async def get_payment_status_route(
    payment_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> PaymentStatusResponse:
    """
    Obtiene el estado actual de un pago para polling.
    """
    payment_repo = PaymentRepository()
    try:
        return await get_payment_status(
            session,
            payment_id=payment_id,
            payment_repo=payment_repo,
        )
    except PaymentIntentNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# Fin del archivo backend/app/modules/payments/routes/payments.py

