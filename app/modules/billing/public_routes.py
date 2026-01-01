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


# Unified 404 response to prevent information leakage
# Both "not found" and "expired" return identical body
_PUBLIC_NOT_FOUND = {
    "error": "not_found",
    "message": "Not found",
}


def _sanitize_dict_for_public(
    data: dict,
    allowed_keys: set[str],
) -> dict:
    """
    Sanitize a dictionary to only include allowed keys (whitelist approach).
    
    Args:
        data: Original dictionary
        allowed_keys: Set of keys that are safe to expose publicly
        
    Returns:
        Sanitized dictionary with only allowed keys
    """
    return {k: v for k, v in data.items() if k in allowed_keys}


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
        
    Security:
        Both "not found" and "expired" return identical error body
        to prevent token enumeration attacks.
    """
    # Buscar por token
    result = await session.execute(
        select(BillingInvoice).where(
            BillingInvoice.public_token == token
        )
    )
    invoice = result.scalar_one_or_none()
    
    if not invoice:
        # Log distinguishes reason, but response is generic
        logger.warning("Public receipt token not found: token=%s...", token[:8] if token else "")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_PUBLIC_NOT_FOUND,
        )
    
    # Verificar expiración
    now = datetime.now(timezone.utc)
    if invoice.public_token_expires_at and invoice.public_token_expires_at <= now:
        # Log distinguishes reason, but response is identical to not_found
        logger.warning(
            "Public receipt token expired: invoice=%s expired_at=%s",
            invoice.invoice_number,
            invoice.public_token_expires_at,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_PUBLIC_NOT_FOUND,
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
            detail=_PUBLIC_NOT_FOUND,
        )
    
    # Generar PDF desde snapshot
    from .utils.pdf_receipt_generator import generate_invoice_pdf, InvoiceSnapshot
    
    snap = invoice.snapshot_json or {}
    
    # Sanitize issuer for PDF: only name/country, NO email (privacy by design)
    issuer_public = _sanitize_dict_for_public(
        snap.get("issuer", {}),
        {"name", "country"},  # email excluded for public PDF
    )
    
    # Sanitize bill_to for PDF: only name, no RFC/address/email
    bill_to_public = _sanitize_dict_for_public(
        snap.get("bill_to", {}),
        {"name"},
    )
    
    # Sanitize line_items: only description, quantity, unit_price, total
    line_items_public = [
        _sanitize_dict_for_public(item, {"description", "quantity", "unit_price", "total", "credits"})
        for item in snap.get("line_items", [])
    ]
    
    # Sanitize totals: only amount fields
    totals_public = _sanitize_dict_for_public(
        snap.get("totals", {}),
        {"subtotal", "tax", "total", "currency"},
    )
    
    # Sanitize payment_details: only provider and status, no stripe IDs
    payment_public = _sanitize_dict_for_public(
        snap.get("payment_details", {}),
        {"provider", "status"},
    )
    
    # Sanitize notes: only public-facing notes (footer, terms)
    # With defensive handling: type check, strip, and length limit
    notes_raw = snap.get("notes", {})
    notes_public = _sanitize_dict_for_public(
        notes_raw if isinstance(notes_raw, dict) else {},
        {"footer", "terms"},
    )
    # Truncate note fields to avoid accidental data dumps
    _MAX_NOTE_LENGTH = 1000
    for key in ("footer", "terms"):
        if isinstance(notes_public.get(key), str):
            notes_public[key] = notes_public[key].strip()[:_MAX_NOTE_LENGTH]
    
    snapshot = InvoiceSnapshot(
        invoice_number=invoice.invoice_number,
        issued_at=invoice.issued_at,
        paid_at=invoice.paid_at,
        issuer=issuer_public,
        bill_to=bill_to_public,
        line_items=line_items_public,
        totals=totals_public,
        payment_details=payment_public,
        notes=notes_public,
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
    totals = snap.get("totals", {})
    line_items = snap.get("line_items", [])
    
    # Calculate credits from line_items if available
    total_credits = sum(item.get("credits", 0) for item in line_items)
    
    # Build strictly whitelisted public response
    # SECURITY: No PII, no RFC/tax_id, no address, no email, no stripe IDs
    response_data = {
        # Invoice identification
        "invoice_number": invoice.invoice_number,
        "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        
        # Amount info (public)
        "amount": totals.get("total"),
        "currency": totals.get("currency"),
        "credits": total_credits if total_credits > 0 else None,
        
        # Payment status (no IDs)
        "payment_provider": snap.get("payment_details", {}).get("provider"),
        "payment_status": snap.get("payment_details", {}).get("status"),
        
        # Minimal bill_to (name only, no PII)
        "bill_to_name": snap.get("bill_to", {}).get("name"),
    }
    
    logger.info(
        "Public receipt JSON accessed: invoice=%s token=%s...",
        invoice.invoice_number,
        token[:8],
    )
    
    return JSONResponse(content=response_data)


__all__ = ["router"]
