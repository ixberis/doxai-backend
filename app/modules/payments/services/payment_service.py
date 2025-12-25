
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/payment_service.py

Servicio de alto nivel para pagos (payments).

Flujos cubiertos:
- Crear registro de pago (inicio de checkout) de forma idempotente
- Marcar pago como succeeded / failed / cancelled
- Acreditar créditos al usuario tras éxito (ledger)

Autor: Ixchel Beristain
Fecha: 2025-11-20
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import (
    PaymentStatus,
    PaymentProvider,
    Currency,
)
from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.repositories.wallet_repository import WalletRepository
from app.modules.payments.services.wallet_service import WalletService
from app.modules.payments.services.credit_service import CreditService

if TYPE_CHECKING:
    from app.modules.payments.models.payment_models import Payment


class PaymentService:
    """
    Servicio para gestionar el ciclo de vida de un pago
    y su integración con el ledger de créditos.
    """

    def __init__(
        self,
        payment_repo: PaymentRepository,
        wallet_repo: WalletRepository,
        wallet_service: WalletService,
        credit_service: CreditService,
    ) -> None:
        self.payment_repo = payment_repo
        self.wallet_repo = wallet_repo
        self.wallet_service = wallet_service
        self.credit_service = credit_service

    # ------------------------------------------------------------------ #
    # Obtener payment por ID
    # ------------------------------------------------------------------ #
    async def get_payment_by_id(
        self,
        session: AsyncSession,
        payment_id: int,
    ) -> Optional["Payment"]:
        """Obtiene un pago por su ID."""
        return await self.payment_repo.get(session, payment_id)

    # ------------------------------------------------------------------ #
    # Inicio de pago (checkout) - idempotente por idempotency_key
    # ------------------------------------------------------------------ #
    async def create_payment(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        provider: PaymentProvider,
        currency: Currency,
        amount: float,
        credits_awarded: int,
        idempotency_key: str,
        payment_intent_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> "Payment":
        """
        Crea un registro de pago en estado CREATED de forma idempotente.
        """
        existing = await self.payment_repo.get_by_idempotency_key(
            session, idempotency_key
        )
        if existing:
            return existing

        payment = await self.payment_repo.create(
            session,
            user_id=user_id,
            provider=provider,
            status=PaymentStatus.CREATED,
            currency=currency,
            amount=amount,
            credits_awarded=credits_awarded,
            payment_intent_id=payment_intent_id,
            idempotency_key=idempotency_key,
            metadata_json=metadata or {},
        )
        return payment

    # ------------------------------------------------------------------ #
    # Actualizaciones de estado
    # ------------------------------------------------------------------ #
    async def mark_pending(
        self,
        session: AsyncSession,
        payment: "Payment",
    ) -> "Payment":
        if payment.status == PaymentStatus.PENDING:
            return payment
        payment.status = PaymentStatus.PENDING
        await session.flush()
        return payment

    async def mark_failed(
        self,
        session: AsyncSession,
        payment: "Payment",
        reason: str | None = None,
    ) -> "Payment":
        """
        Marca el pago como FAILED.
        No toca créditos, porque nunca se acreditaron.
        """
        if payment.status in (
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
            PaymentStatus.REFUNDED,
        ):
            return payment

        payment.status = PaymentStatus.FAILED
        if reason:
            metadata = payment.metadata_json or {}
            metadata.setdefault("errors", [])
            metadata["errors"].append({"reason": reason})
            payment.metadata_json = metadata
        await session.flush()
        return payment

    async def mark_cancelled(
        self,
        session: AsyncSession,
        payment: "Payment",
        reason: str | None = None,
    ) -> "Payment":
        """
        Marca el pago como CANCELLED (p.ej. usuario abandona checkout).
        """
        if payment.status in (
            PaymentStatus.CANCELLED,
            PaymentStatus.FAILED,
            PaymentStatus.REFUNDED,
        ):
            return payment

        payment.status = PaymentStatus.CANCELLED
        if reason:
            metadata = payment.metadata_json or {}
            metadata.setdefault("cancelled", [])
            metadata["cancelled"].append({"reason": reason})
            payment.metadata_json = metadata
        await session.flush()
        return payment

    # ------------------------------------------------------------------ #
    # Éxito de pago: acreditación de créditos
    # ------------------------------------------------------------------ #
    async def apply_success(
        self,
        session: AsyncSession,
        payment: "Payment",
    ) -> "Payment":
        """
        Aplica efectos de un pago exitoso:
        - Si ya está SUCCEEDED/REFUNDED → idempotente, no hace nada.
        - Acredita créditos en la wallet del usuario via CreditService.
        - Cambia el estado a SUCCEEDED.
        """
        if payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED):
            return payment

        # Obtener/crear wallet del usuario
        from app.modules.payments.enums import Currency as CurrencyEnum

        wallet = await self.wallet_service.get_or_create_wallet(
            session,
            user_id=payment.user_id,
            default_currency=payment.currency or CurrencyEnum.MXN,
        )

        # Acreditar créditos (idempotente por operation_id)
        op_id = f"payment:{payment.id}:success"
        await self.credit_service.apply_credit(
            session,
            wallet_id=wallet.id,
            amount=payment.credits_awarded,
            operation_id=op_id,
            metadata={"payment_id": payment.id},
        )

        payment.status = PaymentStatus.SUCCEEDED
        await session.flush()
        return payment
    
# Fin del archivo backend\app\modules\payments\services\payment_service.py
