
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/wallet.py

Ruta para consultar la wallet del usuario.

Endpoint:
- GET /payments/wallet

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.payments.schemas import WalletOut
from app.modules.payments.enums import Currency
from app.modules.payments.repositories import (
    WalletRepository,
    CreditTransactionRepository,
)
from app.modules.payments.services import WalletService, CreditService

router = APIRouter(
    prefix="/wallet",
    tags=["payments:wallet"],
)


def build_wallet_services() -> tuple[WalletRepository, CreditTransactionRepository, WalletService]:
    wallet_repo = WalletRepository()
    credit_repo = CreditTransactionRepository()
    credit_service = CreditService(credit_repo)
    wallet_service = WalletService(wallet_repo=wallet_repo, credit_repo=credit_repo)
    return wallet_repo, credit_repo, wallet_service


@router.get(
    "",
    response_model=WalletOut,
)
async def get_wallet(
    session: AsyncSession = Depends(get_async_session),
):
    """
    Obtiene la wallet del usuario actual.

    NOTA: Por ahora user_id es un placeholder; integrar con Auth más adelante.
    """
    user_id = "demo-user"  # TODO: reemplazar con usuario autenticado real

    wallet_repo, credit_repo, wallet_service = build_wallet_services()

    # Crear u obtener wallet (por ahora siempre MXN)
    wallet = await wallet_service.get_or_create_wallet(
        session,
        user_id=user_id,
        default_currency=Currency.MXN,
    )

    balance = await credit_repo.compute_balance(session, wallet.id)
    balance_reserved = wallet.balance_reserved or 0
    balance_available = max(0, balance - balance_reserved)

    return WalletOut(
        id=wallet.id,
        user_id=wallet.user_id,
        currency=wallet.currency,
        balance=balance,
        balance_reserved=balance_reserved,
        balance_available=balance_available,
    )
# Fin del archivo backend/app/modules/payments/routes/wallet.py