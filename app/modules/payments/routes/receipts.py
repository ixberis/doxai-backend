
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/receipts.py

Rutas para generación y consulta de recibos de pagos.

Endpoints:
- POST /payments/{payment_id}/receipts
- GET  /payments/{payment_id}/receipt-url

Autor: Ixchel Beristain
Fecha: 2025-11-21 (ajustado)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.payments.facades.receipts import (
    generate_receipt,
    get_receipt_url,
)

router = APIRouter(
    tags=["payments:receipts"],
)


class BillingInfo(BaseModel):
    name: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    tax_id: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)


class CompanyInfo(BaseModel):
    name: Optional[str] = Field(default=None)
    tax_id: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)


class ReceiptGenerateRequest(BaseModel):
    user_billing_info: Optional[BillingInfo] = None
    company_info: Optional[CompanyInfo] = None
    force_regenerate: bool = False


@router.post(
    "/payments/{payment_id}/receipts",
    status_code=status.HTTP_200_OK,  # los tests esperan HTTPStatus.OK
    response_model=Dict[str, Any],
)
async def generate_receipt_route(
    payment_id: int,
    payload: ReceiptGenerateRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Genera o regenera un recibo para un pago.
    """
    try:
        result = await generate_receipt(
            session,
            payment_id=payment_id,
            user_billing_info=(
                payload.user_billing_info.model_dump()
                if payload.user_billing_info
                else None
            ),
            company_info=(
                payload.company_info.model_dump()
                if payload.company_info
                else None
            ),
            force_regenerate=payload.force_regenerate,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/payments/{payment_id}/receipt-url",
    response_model=str,
)
async def get_receipt_url_route(
    payment_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> str:
    """
    Obtiene la URL firmada del recibo de un pago.
    """
    try:
        url = await get_receipt_url(session, payment_id=payment_id)
        return url
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Fin del archivo backend/app/modules/payments/routes/receipts.py