
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/payments/refunds/__init__.py

Fachadas de alto nivel para flujos de reembolso.

Expone:
- refund: función principal para iniciar un refund (entry point para tests/rutas)
- refund_via_provider: capa de abstracción sobre el adaptador de refunds
- process_manual_refund: flujo de refund manual (negocio interno).

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.enums import PaymentProvider, Currency, PaymentStatus
from app.modules.payments.adapters.refund_adapters import execute_refund
from app.modules.payments.models.payment_models import Payment
from app.modules.payments.models.refund_models import Refund

from app.modules.payments.repositories.payment_repository import PaymentRepository
from app.modules.payments.repositories.refund_repository import RefundRepository
from app.modules.payments.repositories.wallet_repository import WalletRepository
from app.modules.payments.repositories.credit_transaction_repository import (
    CreditTransactionRepository,
)
from app.modules.payments.services.payment_service import PaymentService
from app.modules.payments.services.refund_service import RefundService
from app.modules.payments.services.wallet_service import WalletService
from app.modules.payments.services.credit_service import CreditService

from .refund_flow import process_manual_refund
from .refund_credits import calcular_creditos_a_revertir, revertir_creditos
from . import refund_provider  # importar el módulo, no la función directamente


async def refund(
    session: AsyncSession,
    *,
    payment_id: int,
    amount_cents: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    reason: Optional[str] = None,
    # Dependency injection for testing
    payment_service: Optional[Any] = None,
    credit_service: Optional[Any] = None,
    refund_service: Optional[Any] = None,
    provider_refund_fn: Optional[Any] = None,  # inyección del stub de proveedor
) -> Tuple[Refund, Payment]:
    """
    Función principal para procesar un refund completo.
    
    Retorna (refund_object, updated_payment).
    
    Parámetros:
    - payment_id: ID del pago a reembolsar
    - amount_cents: monto a reembolsar (None = total)
    - idempotency_key: clave para idempotencia
    - reason: razón del refund
    - payment_service: (opcional) servicio de pagos inyectado (para tests)
    - credit_service: (opcional) servicio de créditos inyectado (para tests)
    - refund_service: (opcional) servicio de refunds inyectado (para tests)
    """
    # Construir repositorios y servicios si no fueron inyectados
    if payment_service is None or credit_service is None or refund_service is None:
        payment_repo = PaymentRepository()
        refund_repo = RefundRepository()
        wallet_repo = WalletRepository()
        credit_repo = CreditTransactionRepository()

        if credit_service is None:
            credit_service = CreditService(credit_repo)
        if payment_service is None:
            wallet_service = WalletService(wallet_repo=wallet_repo, credit_repo=credit_repo)
            payment_service = PaymentService(
                payment_repo=payment_repo,
                wallet_repo=wallet_repo,
                wallet_service=wallet_service,
                credit_service=credit_service,
            )
        if refund_service is None:
            refund_service = RefundService(
                refund_repo=refund_repo,
                payment_repo=payment_repo,
                credit_service=credit_service,
            )

    # 1) Obtener payment (usando el servicio para compatibilidad con tests)
    payment = await payment_service.get_payment_by_id(session, payment_id)
    if not payment:
        raise ValueError(f"Payment {payment_id} not found")

    # 2) Determinar amount_cents (None = total)
    if amount_cents is None:
        # El objeto payment puede tener amount (Decimal) o amount_cents (int)
        if hasattr(payment, 'amount_cents'):
            amount_cents = payment.amount_cents
        elif hasattr(payment, 'amount'):
            amount_cents = int(payment.amount * 100)
        else:
            raise ValueError("Payment object missing amount/amount_cents attribute")
    
    if amount_cents <= 0:
        raise ValueError("amount_cents must be > 0")

    # 3) Validar límites (si aplica)
    await refund_service.validate_refund_limits(payment, Decimal(amount_cents) / 100)

    # 4) Idempotencia: verificar si ya existe refund
    if idempotency_key:
        existing_refund = await refund_service.find_by_idempotency_key(
            payment_id=payment_id, idempotency_key=idempotency_key
        )
        if existing_refund:
            return existing_refund, payment

    # 5) Crear refund interno - llamar al stub (inyectado o por defecto)
    _provider_fn = provider_refund_fn or refund_provider.provider_refund_stub
    try:
        provider_refund_id, provider_confirmed = await _provider_fn(
            payment_id=payment_id,
            amount=Decimal(amount_cents) / 100,
        )
        provider_status_raw = "succeeded" if provider_confirmed else "pending"
    except Exception as e:
        # Si falla, propagar error
        raise

    # 6) Calcular créditos a revertir
    credits_to_reverse = calcular_creditos_a_revertir(
        payment=payment,
        refund_amount_cents=amount_cents,
        provider_confirmed=provider_confirmed,
    )

    # 7) Crear registro de refund
    refund_obj = await refund_service.create_refund(
        session,
        payment=payment,
        amount=Decimal(amount_cents) / 100,
        credits_reversed=credits_to_reverse,
        currency=Currency(payment.currency.value if hasattr(payment.currency, 'value') else payment.currency),
        provider_refund_id=provider_refund_id,
        idempotency_key=idempotency_key,
    )

    # 8) Revertir créditos si aplica
    if provider_confirmed and credits_to_reverse > 0:
        await revertir_creditos(
            credit_service=credit_service,
            payment=payment,
            refund_id=refund_obj.id,
            refund_amount_cents=amount_cents,
            credits_to_reverse=credits_to_reverse,
            reason=reason,
            idempotency_key=idempotency_key,
        )

    # 9) Actualizar estado del payment (solo si confirmed)
    payment_amount_cents = payment.amount_cents if hasattr(payment, 'amount_cents') else int(payment.amount * 100)
    is_full_refund = (amount_cents >= payment_amount_cents)
    
    # Solo marcar como REFUNDED si es full refund Y está confirmado por el proveedor
    if provider_confirmed and is_full_refund:
        new_payment_status = PaymentStatus.REFUNDED
    else:
        # Mantener status actual si pending o parcial
        new_payment_status = payment.status
    
    credits_reversed_total = (payment.payment_metadata or {}).get("credits_reversed_total", 0)
    credits_reversed_total += credits_to_reverse

    updated_payment = await payment_service.update_payment_status(
        payment_id=payment_id,
        new_status=new_payment_status,
        payment_metadata={
            **(payment.payment_metadata or {}),
            "credits_reversed_total": credits_reversed_total,
        },
        refunded_at=None,
    )

    # 10) Marcar refund como completado solo si está confirmado
    if provider_confirmed:
        refund_obj.mark_refunded(provider_refund_id=provider_refund_id, meta={"status": provider_status_raw})
    else:
        # Si está pending, solo actualizar metadata pero mantener status PENDING
        refund_obj.refund_metadata = (refund_obj.refund_metadata or {}) | {"status": provider_status_raw, "provider_refund_id": provider_refund_id}
        if provider_refund_id and not refund_obj.provider_refund_id:
            refund_obj.provider_refund_id = provider_refund_id

    return refund_obj, updated_payment


async def refund_via_provider(
    *,
    provider: PaymentProvider,
    provider_payment_id: str,
    amount_cents: int,
    currency: Currency,
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    provider_transaction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Capa de abstracción para llamar al proveedor de pago.

    - En producción delega en execute_refund (adaptador v3, stub seguro).
    - En tests se monkeypatchea para simular errores de proveedor.

    Parámetros (compatibles con tests):

      provider_payment_id      → ID de intent/orden en el proveedor
      provider_transaction_id  → ID de transacción/captura (PayPal)
      amount_cents             → monto en centavos
    """
    return await execute_refund(
        provider=provider,
        provider_payment_id=provider_payment_id,
        provider_transaction_id=provider_transaction_id,
        amount_cents=amount_cents,
        currency=currency,
        reason=reason,
        metadata=metadata,
        idempotency_key=idempotency_key,
    )


# Opcional: helper de alto nivel para refund manual que utilice los servicios reales.
# Si ya tienes una implementación en refund_flow.py, puedes seguir usándola.
# Aquí te muestro cómo podrías orquestar usando process_manual_refund si necesitas
# exponer una API más sencilla desde este paquete.

async def process_manual_refund_entrypoint(
    session: AsyncSession,
    *,
    payment_id: int,
    amount_cents: Optional[int],
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Punto de entrada simplificado para refunds manuales, pensado para rutas.

    - Construye repos y servicios necesarios.
    - Invoca la lógica de negocio en refund_flow.process_manual_refund().
    """

    payment_repo = PaymentRepository()
    refund_repo = RefundRepository()
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

    # Normalizamos amount_cents → Decimal
    if amount_cents is None:
        # en flujo manual, amount_cents None puede significar "total"
        payment = await payment_repo.get(session, payment_id)
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found")
        total_cents = int(payment.amount * 100)
        amount_cents = total_cents

    if amount_cents <= 0:
        raise ValueError("amount_cents must be > 0")

    amount = Decimal(amount_cents) / Decimal("100")

    refund = await process_manual_refund(
        session,
        payment_id=payment_id,
        amount=amount,
        refund_repo=refund_repo,
        refund_service=refund_service,
        payment_repo=payment_repo,
        wallet_repo=wallet_repo,
        payment_service=payment_service,
    )

    # Empaquetamos una respuesta simple (los tests de flujo unitario suelen
    # centrarse en que no reviente y/o en efectos sobre Payment/Refund).
    return {
        "refund_id": refund.id,
        "payment_id": refund.payment_id,
        "status": refund.status.value,
        "amount_cents": amount_cents,
    }



__all__ = [
    "refund",  # función principal entry point
    "refund_via_provider",
    "process_manual_refund",
    "process_manual_refund_entrypoint",
]

# Fin del archivo backend/app/modules/payments/facades/payments/refunds/__init__.py
