
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/refund_service.py

Servicio para gestionar reembolsos (refunds).

Flujos cubiertos:
- Registrar solicitud de refund (registro interno)
- Aplicar refund exitoso:
    - marcar refund como REFUNDED
    - actualizar estado del payment
    - revertir créditos en el ledger (reverse_credit)

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import RefundStatus, PaymentStatus, Currency
from app.modules.payments.repositories.refund_repository import RefundRepository
from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.services.credit_service import CreditService

if TYPE_CHECKING:
    from app.modules.payments.models.refund_models import Refund
    from app.modules.payments.models.payment_models import Payment


class RefundService:
    """
    Servicio de reembolsos: integra refunds con payments y ledger.
    """

    def __init__(
        self,
        refund_repo: RefundRepository,
        payment_repo: PaymentRepository,
        credit_service: CreditService,
    ) -> None:
        self.refund_repo = refund_repo
        self.payment_repo = payment_repo
        self.credit_service = credit_service

    # ------------------------------------------------------------------ #
    # Registrar refund (pending) de forma idempotente
    # ------------------------------------------------------------------ #
    async def create_refund(
        self,
        session: AsyncSession,
        *,
        payment: "Payment",
        amount: float,
        credits_reversed: int,
        currency: Currency,
        provider_refund_id: Optional[str],
    ) -> "Refund":
        """
        Registra un refund en estado PENDING.

        Idempotencia:
        - Si existe provider_refund_id, se regresa el existente.
        """
        if provider_refund_id:
            existing = await self.refund_repo.get_by_provider_refund_id(
                session, provider_refund_id
            )
            if existing:
                return existing

        refund = await self.refund_repo.create(
            session,
            payment_id=payment.id,
            status=RefundStatus.PENDING,
            currency=currency,
            amount=amount,
            credits_reversed=credits_reversed,
            provider_refund_id=provider_refund_id,
            metadata_json={},
        )
        return refund

    # ------------------------------------------------------------------ #
    # Aplicar refund exitoso
    # ------------------------------------------------------------------ #
    async def apply_success(
        self,
        session: AsyncSession,
        refund: "Refund",
        *,
        wallet_id: int,
    ) -> "Refund":
        """
        Aplica efectos de un refund exitoso:
        - Cambia refund.status → REFUNDED
        - Cambia payment.status → REFUNDED (si estaba SUCCEEDED)
        - Reversa créditos en el ledger (reverse_credit)

        Idempotente: si refund ya está REFUNDED, no hace nada.
        """
        if refund.status == RefundStatus.REFUNDED:
            return refund

        # Revertir créditos (ledger)
        op_id = f"refund:{refund.id}:reverse"
        await self.credit_service.reverse_credit(
            session,
            wallet_id=wallet_id,
            amount=refund.credits_reversed,
            operation_id=op_id,
            metadata={"refund_id": refund.id, "payment_id": refund.payment_id},
        )

        # Marcar refund como REFUNDED
        refund.status = RefundStatus.REFUNDED

        # Actualizar estado del payment
        payment = await self.payment_repo.get(session, refund.payment_id)
        if payment and payment.status == PaymentStatus.SUCCEEDED:
            payment.status = PaymentStatus.REFUNDED

        await session.flush()
        return refund

    # ------------------------------------------------------------------ #
    # Marcar refund como FAILED / CANCELLED
    # ------------------------------------------------------------------ #
    async def mark_failed(
        self,
        session: AsyncSession,
        refund: "Refund",
        reason: str | None = None,
    ) -> "Refund":
        if refund.status in (RefundStatus.FAILED, RefundStatus.CANCELLED):
            return refund

        refund.status = RefundStatus.FAILED
        if reason:
            meta = refund.metadata_json or {}
            meta.setdefault("errors", [])
            meta["errors"].append({"reason": reason})
            refund.metadata_json = meta

        await session.flush()
        return refund

    async def mark_cancelled(
        self,
        session: AsyncSession,
        refund: "Refund",
        reason: str | None = None,
    ) -> "Refund":
        if refund.status in (RefundStatus.FAILED, RefundStatus.CANCELLED):
            return refund

        refund.status = RefundStatus.CANCELLED
        if reason:
            meta = refund.metadata_json or {}
            meta.setdefault("cancelled", [])
            meta["cancelled"].append({"reason": reason})
            refund.metadata_json = meta

        await session.flush()
        return refund

# Fin del archivo backend\app\modules\payments\services\refund_service.py
