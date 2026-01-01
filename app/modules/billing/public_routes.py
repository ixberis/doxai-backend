# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/public_routes.py

Rutas públicas de billing (no requieren autenticación).

Endpoints:
- GET /api/billing/receipts/public/{token}.pdf
- GET /api/billing/receipts/public/{token}.json

Estos endpoints permiten acceso a recibos via token público
generado para compartir en emails de confirmación de compra.

Autor: DoxAI
Fecha: 2026-01-01
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.shared.database.database import get_async_session
from .models_invoice import BillingInvoice
from .models import CheckoutIntent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/billing/receipts/public",
    tags=["billing:public"],
)


async def _get_invoice_by_public_token(
    session: AsyncSession,
    token: str,
) -> BillingInvoice:
    """
    Obtiene invoice por token público, validando expiración.
    
    Args:
        session: Sesión de base de datos
        token: Token público (sin extensión)
        
    Returns:
        BillingInvoice válido
        
    Raises:
        HTTPException 404: Token no encontrado o expirado
    """
    # Buscar por token
    result = await session.execute(
        select(BillingInvoice).where(
            BillingInvoice.public_token == token
        )
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        logger.warning("Public receipt token not found: token=%s...", token[:8] if token else "")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "receipt_not_found",
                "message": "Receipt not found or link has expired",
            },
        )
    
    # Verificar expiración
    now = datetime.now(timezone.utc)
    if invoice.public_token_expires_at and invoice.public_token_expires_at <= now:
        logger.warning(
            "Public receipt token expired: invoice=%s expired_at=%s",
            invoice.invoice_number,
            invoice.public_token_expires_at,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "receipt_expired",
                "message": "This receipt link has expired. Please request a new link.",
            },
        )
    
    return invoice


@router.get(
    "/{token}.pdf",
    status_code=status.HTTP_200_OK,
    summary="Descargar recibo PDF público",
    description="""
    Descarga un recibo PDF usando un token público.
    
    No requiere autenticación. El token tiene un TTL configurable.
    """,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF del recibo generado",
        },
        404: {"description": "Token no encontrado o expirado"},
    },
)
async def get_public_receipt_pdf(
    token: str,
    session: AsyncSession = Depends(get_async_session),
) -> Response:
    """
    Descarga recibo PDF por token público.
    
    Args:
        token: Token público del invoice (sin .pdf)
        session: Sesión de base de datos
        
    Returns:
        Response con PDF binario
        
    Raises:
        404: Token no encontrado o expirado
    """
    invoice = await _get_invoice_by_public_token(session, token)
    
    # Obtener checkout intent para datos adicionales
    intent_result = await session.execute(
        select(CheckoutIntent).where(
            CheckoutIntent.id == invoice.checkout_intent_id
        )
    )
    intent = intent_result.scalar_one_or_none()
    
    if not intent:
        logger.error("Checkout intent not found for invoice: invoice=%s", invoice.invoice_number)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "receipt_not_found", "message": "Receipt data not found"},
        )
    
    # Generar PDF desde snapshot
    from .utils.pdf_receipt_generator import generate_invoice_pdf, InvoiceSnapshot
    
    snap = invoice.snapshot_json or {}
    snapshot = InvoiceSnapshot(
        invoice_number=invoice.invoice_number,
        issued_at=invoice.issued_at,
        paid_at=invoice.paid_at,
        issuer=snap.get("issuer", {}),
        bill_to=snap.get("bill_to", {}),
        line_items=snap.get("line_items", []),
        totals=snap.get("totals", {}),
        payment_details=snap.get("payment_details", {}),
        notes=snap.get("notes", {}),
    )
    
    pdf_bytes = generate_invoice_pdf(snapshot)
    
    # Nombre de archivo
    filename = f"doxai-receipt-{invoice.invoice_number}.pdf"
    
    logger.info(
        "Public receipt PDF accessed: invoice=%s token=%s...",
        invoice.invoice_number,
        token[:8],
    )
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/{token}.json",
    status_code=status.HTTP_200_OK,
    summary="Obtener recibo JSON público",
    description="""
    Obtiene los datos del recibo en formato JSON usando un token público.
    
    No requiere autenticación. El token tiene un TTL configurable.
    """,
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "Datos del recibo en JSON",
        },
        404: {"description": "Token no encontrado o expirado"},
    },
)
async def get_public_receipt_json(
    token: str,
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse:
    """
    Obtiene datos del recibo por token público.
    
    Args:
        token: Token público del invoice (sin .json)
        session: Sesión de base de datos
        
    Returns:
        JSONResponse con datos del recibo
        
    Raises:
        404: Token no encontrado o expirado
    """
    invoice = await _get_invoice_by_public_token(session, token)
    
    snap = invoice.snapshot_json or {}
    
    # Construir respuesta pública (sin datos sensibles)
    response_data = {
        "invoice_number": invoice.invoice_number,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "issuer": snap.get("issuer", {}),
        "bill_to": {
            # Solo exponer nombre, no RFC ni otros datos fiscales
            "name": snap.get("bill_to", {}).get("name"),
        },
        "line_items": snap.get("line_items", []),
        "totals": snap.get("totals", {}),
        "payment_details": {
            "provider": snap.get("payment_details", {}).get("provider"),
            "status": snap.get("payment_details", {}).get("status"),
        },
        "notes": snap.get("notes", {}),
    }
    
    logger.info(
        "Public receipt JSON accessed: invoice=%s token=%s...",
        invoice.invoice_number,
        token[:8],
    )
    
    return JSONResponse(content=response_data)


__all__ = ["router"]
