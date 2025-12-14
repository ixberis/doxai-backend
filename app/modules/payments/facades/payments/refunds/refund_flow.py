
# -*- coding: utf-8 -*-
"""
Entrada de alto nivel para procesar refund manual o vía webhook.

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import Currency
from app.modules.payments.repositories.refund_repository import RefundRepository
from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.repositories.wallet_repository import WalletRepository
from app.modules.payments.services.refund_service import RefundService
from app.modules.payments.services.payment_service import PaymentService
from .refunds_helpers import compute_credits_from_amount
from .refund_provider import provider_refund_stub
from .refund_payment_update import apply_refund_to_payment


async def process_manual_refund(
    session: AsyncSession,
    *,
    payment_id: int,
    amount: Decimal,
    refund_repo: RefundRepository,
    refund_service: RefundService,
    payment_repo: PaymentRepository,
    wallet_repo: WalletRepository,
    payment_service: PaymentService,
):
    """
    Refund manual disparado desde un endpoint administrativo.
    """

    # 1) Obtener payment
    payment = await payment_repo.get(session, payment_id)
    if not payment:
        raise ValueError(f"Payment {payment_id} not found")

    # 2) Calcular créditos a revertir
    credits = compute_credits_from_amount(amount)

    # 3) Crear refund interno
    provider_refund_id = await provider_refund_stub(
        payment_id=payment_id, amount=amount
    )

    refund = await refund_service.create_refund(
        session,
        payment=payment,
        amount=amount,
        credits_reversed=credits,
        currency=Currency(payment.currency),
        provider_refund_id=provider_refund_id,
    )

    # 4) Aplicar refund localmente (ledger + payment)
    await apply_refund_to_payment(
        session,
        refund_service=refund_service,
        payment_service=payment_service,
        payment_repo=payment_repo,
        wallet_repo=wallet_repo,
        refund=refund,
    )

    return refund

# Fin del archivo backend\app\modules\payments\facades\payments\refunds\refund_flow.py
