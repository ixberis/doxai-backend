# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/routes.py

Rutas de billing para paquetes de créditos y checkout.

Endpoints:
- GET /api/billing/credit-packages (público)
- POST /api/billing/checkout/start (auth requerido)
- GET /api/billing/checkout/{intent_id}/status (auth requerido)

Feature flag PAYMENTS_ENABLED:
- False: Retorna URL dummy (desarrollo)
- True: Genera sesión real de Stripe

Autor: DoxAI
Fecha: 2025-12-29
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session
from app.shared.config.settings_payments import get_payments_settings
from app.modules.auth.dependencies import get_current_user_id

from .credit_packages import get_credit_packages, get_package_by_id, CreditPackage
from .schemas import (
    BillingCheckoutRequest,
    BillingCheckoutResponse,
    BillingCheckoutErrorCodes,
    CheckoutStatusResponse,
    CheckoutHistoryItem,
    CheckoutHistoryResponse,
    CheckoutReceiptResponse,
)
from .repository import CheckoutIntentRepository
from .models import CheckoutIntent, CheckoutIntentStatus
from .utils.pdf_receipt_generator import ReceiptData, generate_checkout_receipt_pdf

logger = logging.getLogger(__name__)

# TTL para expiración de intents (60 minutos)
CHECKOUT_INTENT_TTL_MINUTES = 60

router = APIRouter(
    prefix="/billing",
    tags=["billing"],
)


# =============================================================================
# Credit Packages Endpoint (Público)
# =============================================================================

class CreditPackagesResponse(BaseModel):
    """Respuesta con lista de paquetes de créditos."""
    packages: List[CreditPackage]


@router.get(
    "/credit-packages",
    response_model=CreditPackagesResponse,
    summary="Listar paquetes de créditos",
    description="Retorna los paquetes de créditos disponibles. Endpoint público.",
)
async def list_credit_packages() -> CreditPackagesResponse:
    """
    Lista los paquetes de créditos disponibles para compra.
    
    Este endpoint es público (no requiere autenticación) ya que
    solo muestra información de precios.
    """
    packages = get_credit_packages()
    return CreditPackagesResponse(packages=packages)


# =============================================================================
# Checkout Endpoint (Auth requerido)
# =============================================================================

def _get_valid_package_ids() -> set:
    """
    Obtiene los IDs de paquetes válidos desde la fuente de verdad.
    """
    packages = get_credit_packages()
    return {pkg.id for pkg in packages}


def _get_checkout_urls(request: Request, intent_id: int) -> tuple[str, str]:
    """
    Construye URLs de success y cancel para Stripe.
    
    Returns:
        Tuple de (success_url, cancel_url)
    """
    # Obtener base URL del request
    base_url = str(request.base_url).rstrip("/")
    
    # O usar env var si está configurada (para producción)
    frontend_url = os.getenv("FRONTEND_URL", base_url)
    
    success_url = f"{frontend_url}/billing/credits?status=success&intent_id={intent_id}"
    cancel_url = f"{frontend_url}/billing/credits?status=cancelled&intent_id={intent_id}"
    
    return success_url, cancel_url


@router.post(
    "/checkout/start",
    response_model=BillingCheckoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Iniciar checkout de créditos",
    description="""
    Inicia un checkout de créditos prepagados.
    
    **Idempotencia**: Si se envía el mismo idempotency_key para el mismo
    usuario, se retorna el mismo checkout_url sin crear registros duplicados.
    
    **Feature flags**:
    - PAYMENTS_ENABLED=false: Retorna URL dummy (desarrollo)
    - PAYMENTS_ENABLED=true: Genera sesión real de Stripe
    """,
)
async def start_checkout(
    request: Request,
    payload: BillingCheckoutRequest,
    session: AsyncSession = Depends(get_async_session),
    user_id_str: str = Depends(get_current_user_id),
) -> BillingCheckoutResponse:
    """
    Inicia un checkout de créditos prepagados.
    
    Args:
        request: Request para construir URLs
        payload: package_id + idempotency_key
        session: Sesión de base de datos
        user_id_str: User ID del JWT (via get_current_user_id)
        
    Returns:
        BillingCheckoutResponse con checkout_url
        
    Raises:
        401: No autenticado
        422: package_id inválido
    """
    settings = get_payments_settings()
    
    # Convertir user_id a int (DB column es integer/bigint)
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Invalid user_id in token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    repo = CheckoutIntentRepository()
    
    # 1) Validar package_id contra fuente de verdad
    package = get_package_by_id(payload.package_id)
    if package is None:
        valid_ids = _get_valid_package_ids()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": BillingCheckoutErrorCodes.INVALID_PACKAGE,
                "message": f"Package '{payload.package_id}' not found",
                "valid_packages": sorted(valid_ids),
            },
        )
    
    # 2) Crear o recuperar intent existente (idempotencia)
    dummy_checkout_url = "/billing/credits?status=not_ready&intent=pending"
    
    intent, created = await repo.create_or_get_existing(
        session,
        user_id=user_id,
        package_id=payload.package_id,
        idempotency_key=payload.idempotency_key,
        credits_amount=package.credits,
        price_cents=package.price_cents,
        currency=package.currency,
        checkout_url=dummy_checkout_url,
        status=CheckoutIntentStatus.CREATED.value,
        provider=None,
    )
    
    if not created:
        # Intent ya existe - verificar si checkout_url necesita intent_id (backfill)
        if intent.checkout_url and f"intent_id={intent.id}" not in intent.checkout_url:
            # Backfill: URL antigua sin intent_id
            if "intent_id=" not in intent.checkout_url:
                intent.checkout_url = f"{intent.checkout_url}&intent_id={intent.id}"
                await session.commit()
                logger.info(
                    "Backfilled intent_id in checkout_url: intent=%s",
                    intent.id,
                )
        
        logger.info(
            "Idempotent request resolved: user=%s intent=%s",
            user_id,
            intent.id,
        )
        return BillingCheckoutResponse(
            checkout_url=intent.checkout_url,
            checkout_intent_id=intent.id,
        )
    
    # 3) Intent nuevo - determinar si usar Stripe o dummy
    if not settings.payments_enabled:
        # Pagos deshabilitados globalmente
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "payments_disabled",
                "message": "Payments are not enabled on this server",
            },
        )
    
    if not settings.stripe_enabled:
        # Stripe deshabilitado (podría haber otro proveedor en el futuro)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "stripe_disabled",
                "message": "Stripe payments are not enabled",
            },
        )
    
    # Stripe habilitado - crear sesión real
    from .providers.stripe_provider import StripeProvider
    
    provider = StripeProvider()
    
    if not provider.is_configured:
        # Log diagnóstico detallado (sin secretos)
        diag = provider.get_diagnostic_info()
        logger.error(
            "Stripe not configured despite stripe_enabled=True. Diagnostic: %s",
            diag,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "stripe_not_configured",
                "message": "Stripe is enabled but not properly configured",
                "diagnostic": diag,
            },
        )
    
    try:
        success_url, cancel_url = _get_checkout_urls(request, intent.id)
        
        result = await provider.create_checkout_session(
            intent_id=intent.id,
            user_id=user_id,
            package_id=package.id,
            package_name=package.name,
            credits_amount=package.credits,
            price_cents=package.price_cents,
            currency=package.currency,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        
        # Actualizar intent con datos de Stripe
        intent.checkout_url = result.checkout_url
        intent.provider = "stripe"
        intent.status = CheckoutIntentStatus.PENDING.value
        intent.provider_session_id = result.session_id
        
        await session.commit()
        
        logger.info(
            "Created Stripe checkout: user=%s intent=%s session=%s",
            user_id, intent.id, result.session_id,
        )
        
        return BillingCheckoutResponse(
            checkout_url=intent.checkout_url,
            checkout_intent_id=intent.id,
        )
        
    except Exception as e:
        logger.exception("Failed to create Stripe session: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "stripe_session_failed",
                "message": f"Failed to create Stripe checkout session: {str(e)}",
            },
        )


# =============================================================================
# Checkout Status Endpoint (Auth requerido)
# =============================================================================

def _is_intent_expired(intent: CheckoutIntent) -> bool:
    """
    Verifica si el intent debe marcarse como expirado.
    
    Solo expira si:
    - status es 'created' o 'pending'
    - created_at + TTL < now
    """
    if intent.status not in (
        CheckoutIntentStatus.CREATED.value,
        CheckoutIntentStatus.PENDING.value,
    ):
        return False
    
    expiration_time = intent.created_at + timedelta(minutes=CHECKOUT_INTENT_TTL_MINUTES)
    now = datetime.now(timezone.utc)
    
    return now > expiration_time


@router.get(
    "/checkout/{intent_id}/status",
    response_model=CheckoutStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultar estado de checkout",
    description="""
    Consulta el estado actual de un checkout intent.
    
    Solo el dueño del intent puede consultarlo.
    Si el intent tiene más de 60 minutos y status created/pending, 
    se marca automáticamente como expired.
    """,
)
async def get_checkout_status(
    intent_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id_str: str = Depends(get_current_user_id),
) -> CheckoutStatusResponse:
    """
    Obtiene el estado de un checkout intent.
    
    Args:
        intent_id: ID del intent a consultar
        session: Sesión de base de datos
        user_id_str: User ID del JWT
        
    Returns:
        CheckoutStatusResponse con estado actual
        
    Raises:
        401: No autenticado
        404: Intent no existe o no pertenece al usuario
    """
    # Convertir user_id a int
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Invalid user_id in token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Buscar intent por ID y verificar ownership
    result = await session.execute(
        select(CheckoutIntent).where(
            CheckoutIntent.id == intent_id,
            CheckoutIntent.user_id == user_id,
        )
    )
    intent = result.scalar_one_or_none()
    
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "intent_not_found",
                "message": f"Checkout intent {intent_id} not found",
            },
        )
    
    # Verificar expiración y actualizar si corresponde
    if _is_intent_expired(intent):
        intent.status = CheckoutIntentStatus.EXPIRED.value
        await session.commit()
        logger.info(
            "Marked intent as expired: intent=%s user=%s",
            intent.id, user_id,
        )
    
    return CheckoutStatusResponse(
        checkout_intent_id=intent.id,
        status=intent.status,
        provider=intent.provider,
        provider_session_id=intent.provider_session_id,
        credits_amount=intent.credits_amount,
        created_at=intent.created_at,
        updated_at=intent.updated_at,
    )


# =============================================================================
# Checkout History Endpoint (Auth requerido)
# =============================================================================

@router.get(
    "/checkouts",
    response_model=CheckoutHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Historial de checkouts",
    description="""
    Lista los checkouts del usuario autenticado con paginación.
    
    Ordenados por fecha de creación descendente (más recientes primero).
    """,
)
async def list_checkouts(
    limit: int = Query(default=20, ge=1, le=100, description="Límite por página"),
    offset: int = Query(default=0, ge=0, description="Offset para paginación"),
    session: AsyncSession = Depends(get_async_session),
    user_id_str: str = Depends(get_current_user_id),
) -> CheckoutHistoryResponse:
    """
    Lista los checkouts del usuario con paginación.
    
    Args:
        limit: Límite de resultados (1-100)
        offset: Offset para paginación
        session: Sesión de base de datos
        user_id_str: User ID del JWT
        
    Returns:
        CheckoutHistoryResponse con items paginados
        
    Raises:
        401: No autenticado
    """
    # Convertir user_id a int
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Invalid user_id in token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Contar total
    count_result = await session.execute(
        select(func.count(CheckoutIntent.id)).where(
            CheckoutIntent.user_id == user_id
        )
    )
    total = count_result.scalar() or 0
    
    # Obtener items paginados
    items_result = await session.execute(
        select(CheckoutIntent)
        .where(CheckoutIntent.user_id == user_id)
        .order_by(CheckoutIntent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    intents = items_result.scalars().all()
    
    items = [
        CheckoutHistoryItem(
            id=intent.id,
            status=intent.status,
            credits_amount=intent.credits_amount,
            provider=intent.provider,
            created_at=intent.created_at,
            updated_at=intent.updated_at,
        )
        for intent in intents
    ]
    
    return CheckoutHistoryResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Checkout Receipt Endpoint (Auth requerido)
# =============================================================================

@router.get(
    "/checkout/{intent_id}/receipt",
    response_model=CheckoutReceiptResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener recibo de checkout",
    description="""
    Obtiene el recibo de un checkout completado.
    
    Solo disponible para checkouts con status 'completed'.
    El recibo incluye detalles del pago y créditos adquiridos.
    """,
)
async def get_checkout_receipt(
    intent_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id_str: str = Depends(get_current_user_id),
) -> CheckoutReceiptResponse:
    """
    Obtiene el recibo de un checkout completado.
    
    Args:
        intent_id: ID del intent a consultar
        session: Sesión de base de datos
        user_id_str: User ID del JWT
        
    Returns:
        CheckoutReceiptResponse con detalles del pago
        
    Raises:
        401: No autenticado
        404: Intent no existe o no pertenece al usuario
        409: Intent no está completado
    """
    # Convertir user_id a int
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Invalid user_id in token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Buscar intent por ID y verificar ownership
    result = await session.execute(
        select(CheckoutIntent).where(
            CheckoutIntent.id == intent_id,
            CheckoutIntent.user_id == user_id,
        )
    )
    intent = result.scalar_one_or_none()
    
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "intent_not_found",
                "message": f"Checkout intent {intent_id} not found",
            },
        )
    
    # Solo se puede obtener recibo de checkouts completados
    if intent.status != CheckoutIntentStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "checkout_not_completed",
                "message": f"Cannot generate receipt for checkout with status '{intent.status}'",
                "current_status": intent.status,
            },
        )
    
    return CheckoutReceiptResponse(
        checkout_intent_id=intent.id,
        status=intent.status,
        credits_amount=intent.credits_amount,
        price_cents=intent.price_cents,
        currency=intent.currency,
        provider=intent.provider,
        provider_session_id=intent.provider_session_id,
        created_at=intent.created_at,
        completed_at=intent.updated_at,  # updated_at es cuando se completó
    )


# =============================================================================
# Checkout Receipt PDF Endpoint (Auth requerido)
# =============================================================================

@router.get(
    "/checkout/{intent_id}/receipt.pdf",
    status_code=status.HTTP_200_OK,
    summary="Descargar recibo PDF de checkout",
    description="""
    Genera y descarga un recibo PDF de un checkout completado.
    
    Solo disponible para checkouts con status 'completed'.
    El PDF incluye todos los detalles del pago y es válido para auditoría.
    """,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF del recibo generado",
        },
        404: {"description": "Intent no encontrado"},
        409: {"description": "Checkout no completado"},
    },
)
async def get_checkout_receipt_pdf(
    intent_id: int,
    session: AsyncSession = Depends(get_async_session),
    user_id_str: str = Depends(get_current_user_id),
) -> Response:
    """
    Genera y descarga un recibo PDF de un checkout completado.
    
    Args:
        intent_id: ID del intent a consultar
        session: Sesión de base de datos
        user_id_str: User ID del JWT
        
    Returns:
        Response con PDF binario
        
    Raises:
        401: No autenticado
        404: Intent no existe o no pertenece al usuario
        409: Intent no está completado
    """
    # Convertir user_id a int
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "message": "Invalid user_id in token"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Buscar intent por ID y verificar ownership
    result = await session.execute(
        select(CheckoutIntent).where(
            CheckoutIntent.id == intent_id,
            CheckoutIntent.user_id == user_id,
        )
    )
    intent = result.scalar_one_or_none()
    
    if intent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "intent_not_found",
                "message": f"Checkout intent {intent_id} not found",
            },
        )
    
    # Solo se puede obtener recibo de checkouts completados
    if intent.status != CheckoutIntentStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "checkout_not_completed",
                "message": f"Cannot generate receipt for checkout with status '{intent.status}'",
                "current_status": intent.status,
            },
        )
    
    # Obtener nombre del paquete si está disponible
    package = get_package_by_id(intent.package_id) if intent.package_id else None
    package_name = package.name if package else None
    
    # Preparar datos del recibo
    receipt_data = ReceiptData(
        checkout_intent_id=intent.id,
        user_id=user_id,
        credits_amount=intent.credits_amount,
        price_cents=intent.price_cents,
        currency=intent.currency,
        provider=intent.provider,
        provider_session_id=intent.provider_session_id,
        package_id=intent.package_id,
        package_name=package_name,
        created_at=intent.created_at,
        completed_at=intent.updated_at,
    )
    
    # Generar PDF
    pdf_bytes = generate_checkout_receipt_pdf(receipt_data)
    
    # Retornar respuesta con PDF
    filename = f"doxai-receipt-{intent_id}.pdf"
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# Fin del archivo
