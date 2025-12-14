
# -*- coding: utf-8 -*-
"""
backend\app\modules\payments\facades\payments\refunds\refund_payment_update.py

Lógica común para aplicar refund en nuestra BD
utilizando RefundService y PaymentService.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.services.refund_service import RefundService
from app.modules.payments.services.payment_service import PaymentService
from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.repositories.wallet_repository import WalletRepository


async def apply_refund_to_payment(
    session: AsyncSession,
    *,
    refund_service: RefundService,
    payment_service: PaymentService,
    payment_repo: PaymentRepository,
    wallet_repo: WalletRepository,
    refund,
):
    """
    Aplica refund a un payment:
    - Cambia estado del payment
    - Reversa créditos en ledger
    """
    payment = await payment_repo.get(session, refund.payment_id)
    if not payment:
        raise ValueError(f"Payment {refund.payment_id} not found")

    wallet = await wallet_repo.get_by_user_id(session, payment.user_id)
    if not wallet:
        raise ValueError(f"Wallet not found for user={payment.user_id}")

    await refund_service.apply_success(
        session,
        refund=refund,
        wallet_id=wallet.id,
    )

    return refund

# Fin del archivo backend\app\modules\payments\facades\payments\refunds\refund_payment_update.py