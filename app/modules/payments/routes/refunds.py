
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/refunds.py

Rutas para reembolsos manuales (administrativos).

Endpoint:
- POST /payments/refunds/manual

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.payments.schemas import RefundCreate, RefundOut
from app.modules.payments.repositories import (
    RefundRepository,
    PaymentRepository,
    WalletRepository,
    CreditTransactionRepository,
)
from app.modules.payments.services import (
    RefundService,
    PaymentService,
    WalletService,
    CreditService,
)
from app.modules.payments.facades.payments.refunds import process_manual_refund

router = APIRouter(
    prefix="/refunds",
    tags=["payments:refunds"],
)


def build_refund_services():
    refund_repo = RefundRepository()
    payment_repo = PaymentRepository()
    wallet_repo = WalletRepository()
    credit_repo = CreditTransactionRepository()

    credit_service = CreditService(credit_repo)
    wallet_service = WalletService(wallet_repo=wallet_repo, credit_repo=credit_repo)
    payment_service = PaymentService(
        payment_repo=payment_repo,
        wallet_repo=wallet_repo,
        wallet_service=wallet_service,
        credit_service=credit_service,
    )
    refund_service = RefundService(
        refund_repo=refund_repo,
        payment_repo=payment_repo,
        credit_service=credit_service,
    )

    return refund_repo, payment_repo, wallet_repo, refund_service, payment_service


@router.post(
    "/manual",
    response_model=RefundOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_refund(
    payload: RefundCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Crea y aplica un reembolso manual para un pago existente.

    Pensado para endpoints administrativos.
    """
    refund_repo, payment_repo, wallet_repo, refund_service, payment_service = (
        build_refund_services()
    )

    from decimal import Decimal

    try:
        refund = await process_manual_refund(
            session,
            payment_id=payload.payment_id,
            amount=Decimal(payload.amount),
            refund_repo=refund_repo,
            refund_service=refund_service,
            payment_repo=payment_repo,
            wallet_repo=wallet_repo,
            payment_service=payment_service,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return RefundOut(
        id=refund.id,
        payment_id=refund.payment_id,
        currency=refund.currency,
        amount=refund.amount,
        credits_reversed=refund.credits_reversed,
        status=refund.status,
        provider_refund_id=refund.provider_refund_id,
        created_at=refund.created_at,
        updated_at=refund.updated_at,
    )
# Fin del archivo backend/app/modules/payments/routes/refunds.py