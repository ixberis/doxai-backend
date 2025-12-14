
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/wallet_service.py

Servicio para operaciones de alto nivel sobre wallets.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.repositories.wallet_repository import WalletRepository
from app.modules.payments.repositories.credit_transaction_repository import (
    CreditTransactionRepository,
)


class WalletService:
    """
    Servicio de acceso y validación del estado de una wallet.
    No modifica el ledger directo; eso se hace en CreditService.
    """

    def __init__(
        self,
        wallet_repo: WalletRepository,
        credit_repo: CreditTransactionRepository,
    ) -> None:
        self.wallet_repo = wallet_repo
        self.credit_repo = credit_repo

    # ---------------------------------------------------------
    # Obtener o crear wallet del usuario
    # ---------------------------------------------------------
    async def get_or_create_wallet(
        self, session: AsyncSession, user_id: str, default_currency
    ):
        wallet = await self.wallet_repo.get_by_user_id(session, user_id)
        if wallet:
            return wallet

        wallet = await self.wallet_repo.create(
            session,
            user_id=user_id,
            currency=default_currency,
            balance_reserved=0,
        )
        return wallet

    # ---------------------------------------------------------
    # Lecturas seguras de saldo
    # ---------------------------------------------------------
    async def get_balance(self, session: AsyncSession, wallet_id: int) -> int:
        """Balance real usando el ledger SQL."""
        return await self.credit_repo.compute_balance(session, wallet_id)

    async def get_available_credits(
        self, session: AsyncSession, wallet
    ) -> int:
        """Créditos disponibles (balance real - reservados)."""
        balance = await self.get_balance(session, wallet.id)
        return balance - wallet.balance_reserved

    # ---------------------------------------------------------
    # Verificación previa a consumo
    # ---------------------------------------------------------
    async def ensure_sufficient_credits(
        self,
        session: AsyncSession,
        wallet,
        required: int,
    ):
        available = await self.get_available_credits(session, wallet)
        if available < required:
            raise ValueError(
                f"Insufficient credits: required={required}, available={available}"
            )
        return True

    # ---------------------------------------------------------
    # Manejo de balance_reserved (reservas)
    # ---------------------------------------------------------
    async def reserve_credits(
        self, session: AsyncSession, wallet, amount: int
    ):
        """
        Aumenta balance_reserved localmente.
        Se utiliza solo cuando la reserva ya fue creada a nivel SQL.
        """
        wallet.balance_reserved += amount
        await session.flush()

    async def release_reserved(
        self, session: AsyncSession, wallet, amount: int
    ):
        """
        Reduce balance_reserved (reserva liberada o consumida).
        """
        wallet.balance_reserved = max(0, wallet.balance_reserved - amount)
        await session.flush()

# Fin del archivo backend\app\modules\payments\services\wallet_service.py