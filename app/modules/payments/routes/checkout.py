
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/checkout.py

Rutas de inicio de checkout para créditos prepagados.

Endpoint principal:
- POST /payments/checkout/start

ANTI-FRAUDE: Si el request incluye package_id, amount y credits
se resuelven desde billing.get_package_by_id() (fuente de verdad).
Si vienen ambos (package_id + credits/amount), se rechaza con 422.

AUTH (runtime resolution): 
- Producción: Usa auth.dependencies.validate_jwt_token (única fuente de verdad)
- Desarrollo: ALLOW_DEMO_USER=true permite demo-user

Autor: Ixchel Beristain
Fecha: 2025-11-21
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.modules.payments.schemas import CheckoutRequest, CheckoutResponse
from app.modules.payments.repositories import (
    PaymentRepository,
    WalletRepository,
    CreditTransactionRepository,
    RefundRepository,
    PaymentEventRepository,
    UsageReservationRepository,
)
from app.modules.payments.services import (
    PaymentService,
    WalletService,
    CreditService,
    RefundService,
    PaymentEventService,
    ReservationService,
)
from app.modules.payments.enums import Currency
from app.modules.payments.facades.checkout import start_checkout as start_checkout_facade
from app.modules.payments.facades.checkout.dto import CheckoutRequest as FacadeCheckoutRequest
from app.modules.billing.credit_packages import get_package_by_id


# =============================================================================
# Auth dependency - RUNTIME resolution (not import-time)
# =============================================================================

def _is_production() -> bool:
    """Detecta si estamos en entorno de producción."""
    env = os.getenv("ENVIRONMENT", "").lower()
    python_env = os.getenv("PYTHON_ENV", "").lower()
    return env == "production" or python_env == "production"


async def resolve_current_user_id(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    Resuelve el user_id en RUNTIME según el entorno.
    
    - Producción: usa auth.dependencies.validate_jwt_token (única fuente de verdad)
    - Desarrollo/Test: usa stub (permite demo-user o token de prueba)
    
    Esta resolución ocurre en runtime (no import-time) para que
    los tests puedan controlar el entorno con monkeypatch.
    """
    if _is_production():
        # Producción: JWT real obligatorio
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "authentication_required",
                    "message": "Authorization header is required",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token_format",
                    "message": "Authorization header must be 'Bearer <token>'",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = authorization[7:]  # Remove "Bearer "
        
        # Usar auth.dependencies como única fuente de verdad
        from app.modules.auth.dependencies import validate_jwt_token
        return validate_jwt_token(token)
    else:
        # Desarrollo/Test: usar stub
        from .auth_stub import get_current_user_id as stub_get_user
        return await stub_get_user(authorization)


router = APIRouter(
    prefix="/checkout",
    tags=["payments:checkout"],
)


def build_services(session: AsyncSession) -> dict:
    """Helper para instanciar repos y servicios."""
    wallet_repo = WalletRepository()
    credit_repo = CreditTransactionRepository()
    payment_repo = PaymentRepository()
    refund_repo = RefundRepository()
    event_repo = PaymentEventRepository()
    reservation_repo = UsageReservationRepository()

    credit_service = CreditService(credit_repo)
    wallet_service = WalletService(
        wallet_repo=wallet_repo,
        credit_repo=credit_repo,
    )
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
    event_service = PaymentEventService(event_repo=event_repo)
    reservation_service = ReservationService(
        reservation_repo=reservation_repo,
        wallet_repo=wallet_repo,
        wallet_service=wallet_service,
        credit_service=credit_service,
    )

    return {
        "wallet_service": wallet_service,
        "credit_service": credit_service,
        "payment_service": payment_service,
        "refund_service": refund_service,
        "event_service": event_service,
        "reservation_service": reservation_service,
    }


@router.post(
    "/start",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_checkout(
    payload: CheckoutRequest,
    session: AsyncSession = Depends(get_async_session),
    user_id: str = Depends(resolve_current_user_id),
):
    """
    Inicia un checkout de créditos prepagados.

    ANTI-FRAUDE: Si se envía package_id, amount y credits se resuelven
    desde el backend (billing.get_package_by_id). No se permite enviar
    package_id junto con credits/amount (422).

    AUTH (runtime): 
    - Producción: Requiere Bearer JWT válido
    - Desarrollo: ALLOW_DEMO_USER=true permite acceso sin token
    """
    # --- ANTI-FRAUDE: Resolver package_id desde fuente de verdad ---
    if payload.package_id:
        package = get_package_by_id(payload.package_id)
        if package is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_package",
                    "message": f"Package '{payload.package_id}' not found",
                },
            )
        # Usar valores del paquete
        resolved_amount = Decimal(package.price_cents) / 100
        resolved_credits = package.credits
        resolved_currency = Currency(package.currency.lower())
    else:
        # Modo legacy: usa valores del cliente (ya validados por Pydantic)
        resolved_amount = payload.amount
        resolved_credits = payload.credits
        resolved_currency = payload.currency

    # Construir payload para la facade con valores resueltos
    facade_payload = FacadeCheckoutRequest(
        provider=payload.provider,
        currency=resolved_currency,
        credits=resolved_credits,
        amount=resolved_amount,
        idempotency_key=payload.idempotency_key,
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
    )

    services = build_services(session)
    payment_service: PaymentService = services["payment_service"]

    response = await start_checkout_facade(
        session,
        user_id=user_id,
        payload=facade_payload,
        payment_service=payment_service,
    )
    return response


# Fin del archivo backend/app/modules/payments/routes/checkout.py
