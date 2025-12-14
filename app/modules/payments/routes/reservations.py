
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/reservations.py

Rutas para manejar reservas de créditos (UsageReservation).

Endpoints:
- POST /payments/reservations/create
- POST /payments/reservations/consume
- POST /payments/reservations/cancel

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.payments.enums import Currency
from app.modules.payments.schemas import UsageReservationCreate, UsageReservationOut
from app.modules.payments.repositories import (
    WalletRepository,
    CreditTransactionRepository,
    UsageReservationRepository,
)
from app.modules.payments.services import (
    WalletService,
    CreditService,
    ReservationService,
)

router = APIRouter(
    prefix="/reservations",
    tags=["payments:reservations"],
)


class ReservationOperation(BaseModel):
    operation_id: str = Field(
        description="operation_id de la reserva (idempotente).",
    )


def build_reservation_services():
    wallet_repo = WalletRepository()
    credit_repo = CreditTransactionRepository()
    reservation_repo = UsageReservationRepository()

    credit_service = CreditService(credit_repo)
    wallet_service = WalletService(wallet_repo=wallet_repo, credit_repo=credit_repo)
    reservation_service = ReservationService(
        reservation_repo=reservation_repo,
        wallet_repo=wallet_repo,
        wallet_service=wallet_service,
        credit_service=credit_service,
    )
    return wallet_service, reservation_service


@router.post(
    "/create",
    response_model=UsageReservationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    payload: UsageReservationCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Crea una reserva de créditos.

    NOTA: user_id es placeholder; integrar Auth posteriormente.
    """
    user_id = "demo-user"  # TODO: reemplazar por usuario autenticado real
    wallet_service, reservation_service = build_reservation_services()

    wallet = await wallet_service.get_or_create_wallet(
        session,
        user_id=user_id,
        default_currency=Currency.MXN,
    )

    reservation = await reservation_service.create_reservation(
        session,
        wallet_id=wallet.id,
        credits=payload.credits,
        operation_id=payload.operation_id or f"reservation:{wallet.id}:{payload.credits}",
        ttl_minutes=payload.ttl_minutes,
    )

    return UsageReservationOut(
        id=reservation.id,
        status=reservation.status,
        credits_reserved=reservation.credits_reserved,
        operation_id=reservation.operation_id,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
        updated_at=reservation.updated_at,
    )


@router.post("/consume", response_model=UsageReservationOut)
async def consume_reservation(
    payload: ReservationOperation,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Consume una reserva existente (genera débito en ledger).
    """
    _, reservation_service = build_reservation_services()

    try:
        reservation = await reservation_service.consume_reservation(
            session,
            operation_id=payload.operation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return UsageReservationOut(
        id=reservation.id,
        status=reservation.status,
        credits_reserved=reservation.credits_reserved,
        operation_id=reservation.operation_id,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
        updated_at=reservation.updated_at,
    )


@router.post("/cancel", response_model=UsageReservationOut)
async def cancel_reservation(
    payload: ReservationOperation,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Cancela una reserva (libera créditos reservados sin débito).
    """
    _, reservation_service = build_reservation_services()

    try:
        reservation = await reservation_service.cancel_reservation(
            session,
            operation_id=payload.operation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return UsageReservationOut(
        id=reservation.id,
        status=reservation.status,
        credits_reserved=reservation.credits_reserved,
        operation_id=reservation.operation_id,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
        updated_at=reservation.updated_at,
    )
# Fin del archivo backend/app/modules/payments/routes/reservations.py