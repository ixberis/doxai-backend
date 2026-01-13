# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/services/invoice_service.py

Servicio para gestión de invoices/recibos comerciales.

Genera snapshots de recibos estilo OpenAI con:
- Invoice number legible (DOX-YYYY-NNNN)
- Datos de emisor
- Datos del cliente (Bill to)
- Line items
- Totals
- Payment details

Autor: DoxAI
Fecha: 2025-12-31
Updated: 2026-01-12 - SSOT: auth_user_id UUID for intent ownership
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CheckoutIntent
from ..models_invoice import BillingInvoice
from ..credit_packages import get_package_by_id
from app.modules.user_profile.models.tax_profile import UserTaxProfile

logger = logging.getLogger(__name__)


# Datos del emisor (branding para header del PDF)
ISSUER_INFO = {
    "trade_name": "DoxAI",
    "website": "https://doxai.site",
}

# Datos comerciales para el bloque "DE" del recibo (NO fiscal)
RECEIPT_FROM = {
    "name": "JUVARE",
    "country": "México",
    "email": "doxai@doxai.site",
}


def _generate_invoice_number(year: int, sequence: int) -> str:
    """Genera número de recibo legible: DOX-YYYY-NNNN"""
    return f"DOX-{year}-{sequence:04d}"


def _format_price(cents: int, currency: str) -> str:
    """Formatea precio de centavos a string."""
    amount = cents / 100
    if currency.upper() == "MXN":
        return f"${amount:,.2f} MXN"
    elif currency.upper() == "USD":
        return f"${amount:,.2f} USD"
    return f"{amount:,.2f} {currency.upper()}"


def _build_bill_to(
    auth_user_id: UUID,
    user_email: Optional[str] = None,
    user_name: Optional[str] = None,
    tax_profile: Optional[UserTaxProfile] = None,
) -> Dict[str, Any]:
    """
    Construye sección "Bill to" del recibo.
    
    Lógica para determinar el nombre del receptor:
    - Si hay perfil fiscal con use_razon_social=True y razon_social:
      → usar razon_social (compras a nombre de empresa)
    - Si hay perfil fiscal con use_razon_social=False:
      → usar user_name (compras a nombre personal)
    - Si no hay perfil → user_name o email del usuario
    - Edge case (sin datos) → "Usuario #{uuid_prefix}"
    
    IMPORTANTE: Para recibos comerciales (no CFDI), usamos el perfil fiscal
    sin importar el status (draft/active/verified). El status es solo
    para validación de datos fiscales obligatorios para CFDI.
    
    SSOT: Uses auth_user_id (UUID) as primary identifier.
    """
    uuid_prefix = str(auth_user_id)[:8]
    
    # Caso A: Tax profile con datos fiscales
    # Usamos el perfil si existe, sin importar status (recibo comercial, no CFDI)
    if tax_profile:
        # Determinar nombre según use_razon_social
        if tax_profile.use_razon_social and tax_profile.razon_social:
            # Compra a nombre de empresa: usar razón social
            recipient_name = tax_profile.razon_social
        else:
            # Compra a nombre personal: usar nombre del usuario
            recipient_name = user_name or f"Usuario #{uuid_prefix}"
        
        return {
            "auth_user_id": str(auth_user_id),
            "name": recipient_name,
            "rfc": tax_profile.rfc,
            "tax_regime": tax_profile.regimen_fiscal_clave,
            "postal_code": tax_profile.domicilio_fiscal_cp,
            "billing_email": tax_profile.email_facturacion,
            "tax_profile_status": tax_profile.status,  # Para logging/debug
        }
    
    # Caso B: Sin tax profile pero con datos de usuario
    if user_name or user_email:
        return {
            "auth_user_id": str(auth_user_id),
            "name": user_name or f"Usuario #{uuid_prefix}",
            "email": user_email,
        }
    
    # Caso C: Edge case - solo auth_user_id
    return {
        "auth_user_id": str(auth_user_id),
        "name": f"Usuario #{uuid_prefix}",
    }


def _build_line_items(
    package_id: str,
    package_name: Optional[str],
    credits_amount: int,
    price_cents: int,
    currency: str,
) -> list:
    """Construye line items del recibo."""
    unit_price = price_cents  # Por ahora qty=1
    
    return [
        {
            "description": package_name or f"Paquete de créditos ({package_id})",
            "quantity": 1,
            "unit_price_cents": unit_price,
            "total_cents": price_cents,
            "currency": currency.upper(),
            "credits": credits_amount,
        }
    ]


def _build_totals(
    price_cents: int,
    currency: str,
    tax_rate: float = 0.0,
) -> Dict[str, Any]:
    """Construye totales del recibo."""
    subtotal = price_cents
    tax_amount = int(subtotal * tax_rate)
    total = subtotal + tax_amount
    
    return {
        "subtotal_cents": subtotal,
        "tax_rate": tax_rate,
        "tax_amount_cents": tax_amount,
        "total_cents": total,
        "paid_cents": total,
        "currency": currency.upper(),
        "formatted": {
            "subtotal": _format_price(subtotal, currency),
            "tax": _format_price(tax_amount, currency),
            "total": _format_price(total, currency),
            "paid": _format_price(total, currency),
        },
    }


def _build_payment_details(
    intent: CheckoutIntent,
) -> Dict[str, Any]:
    """Construye detalles de pago."""
    return {
        "provider": (intent.provider or "").upper(),
        "provider_session_id": intent.provider_session_id,
        "checkout_intent_id": intent.id,
        "idempotency_key": intent.idempotency_key,
        "status": intent.status,
    }


def _resolve_paid_at(intent: CheckoutIntent) -> Optional[datetime]:
    """
    Resuelve la fecha de pago estable para un intent completado.
    
    Orden de preferencia:
    1. intent.completed_at (campo canónico de BD 2.0)
    2. intent.paid_at (si existe el campo legacy)
    3. intent.created_at (fallback - momento de creación)
    
    NO usar updated_at porque cambia con cualquier modificación.
    """
    # Usar completed_at (campo canónico)
    if hasattr(intent, 'completed_at') and intent.completed_at:
        return intent.completed_at
    
    # Legacy: paid_at
    if hasattr(intent, 'paid_at') and intent.paid_at:
        return intent.paid_at
    
    # Fallback: usar created_at (asume que el pago ocurrió cerca de la creación)
    return intent.created_at


async def get_or_create_invoice(
    session: AsyncSession,
    intent: CheckoutIntent,
    user_email: Optional[str] = None,
    user_name: Optional[str] = None,
) -> BillingInvoice:
    """
    Obtiene o crea invoice para un checkout intent.
    
    Idempotente: si ya existe invoice para el intent, lo retorna.
    Si no, crea uno nuevo con snapshot de datos actuales.
    
    Estrategia de invoice_number (concurrency-safe):
    1. Crear invoice con invoice_number temporal (placeholder)
    2. Flush para obtener invoice.id (autoincrement)
    3. Generar invoice_number = DOX-YYYY-{id:06d}
    4. Actualizar y commit
    
    SSOT: Uses intent.auth_user_id (UUID) for all operations.
    
    Args:
        session: Sesión de base de datos
        intent: CheckoutIntent completado
        user_email: Email del usuario (opcional, para Bill to)
        user_name: Nombre del usuario (opcional, para Bill to)
        
    Returns:
        BillingInvoice existente o recién creado
    """
    from sqlalchemy.exc import IntegrityError
    
    # SSOT: Use auth_user_id from intent
    auth_user_id = intent.auth_user_id
    
    # Verificar si ya existe invoice
    result = await session.execute(
        select(BillingInvoice).where(
            BillingInvoice.checkout_intent_id == intent.id
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Backfill: si bill_to tiene "Usuario #..." o falta email, actualizar con datos reales
        snap = existing.snapshot_json or {}
        bill_to = snap.get("bill_to", {})
        current_name = bill_to.get("name", "")
        current_email = bill_to.get("billing_email") or bill_to.get("email")
        
        needs_backfill = (
            current_name.startswith("Usuario #") or 
            (not current_email and (user_name or user_email))
        )
        
        if needs_backfill and (user_name or user_email):
            # Obtener tax profile para el backfill using auth_user_id
            # NO filtramos por status: recibo comercial puede usar cualquier perfil
            tax_result = await session.execute(
                select(UserTaxProfile).where(
                    UserTaxProfile.auth_user_id == auth_user_id,
                )
            )
            tax_profile = tax_result.scalar_one_or_none()
            
            bill_to_new = _build_bill_to(
                auth_user_id=auth_user_id,
                user_email=user_email,
                user_name=user_name,
                tax_profile=tax_profile,
            )
            
            snap["bill_to"] = bill_to_new
            existing.snapshot_json = snap
            await session.commit()
            await session.refresh(existing)
            
            logger.info(
                "Backfilled bill_to for existing invoice: invoice=%s old_name=%s new_name=%s new_email=%s",
                existing.invoice_number,
                current_name,
                bill_to_new.get("name"),
                bill_to_new.get("billing_email") or bill_to_new.get("email"),
            )
        else:
            logger.debug("Invoice already exists: intent=%s invoice=%s", intent.id, existing.invoice_number)
        
        return existing
    
    # Obtener perfil fiscal del usuario (si existe) using auth_user_id
    # NO filtramos por status: recibo comercial puede usar cualquier perfil
    # El status (draft/active/verified) es solo para validación CFDI
    tax_result = await session.execute(
        select(UserTaxProfile).where(
            UserTaxProfile.auth_user_id == auth_user_id,
        )
    )
    tax_profile = tax_result.scalar_one_or_none()
    
    # Obtener nombre del paquete
    package = get_package_by_id(intent.package_id)
    package_name = package.name if package else None
    
    # Resolver paid_at de forma estable
    paid_at = _resolve_paid_at(intent)
    
    # Construir snapshot (invoice_number se actualizará después)
    now = datetime.now(timezone.utc)
    year = now.year
    
    bill_to = _build_bill_to(
        auth_user_id=auth_user_id,
        user_email=user_email,
        user_name=user_name,
        tax_profile=tax_profile,
    )
    
    # Log detallado para diagnóstico de tax profile
    if tax_profile:
        logger.info(
            "invoice_snapshot_tax_profile_used: auth_user_id=%s use_razon_social=%s razon_social_present=%s rfc_present=%s status=%s",
            str(auth_user_id)[:8] + "...",
            tax_profile.use_razon_social,
            bool(tax_profile.razon_social),
            bool(tax_profile.rfc),
            tax_profile.status,
        )
    else:
        logger.info(
            "invoice_snapshot_tax_profile_missing: auth_user_id=%s fallback_name=%s",
            str(auth_user_id)[:8] + "...",
            user_name or "Usuario #" + str(auth_user_id)[:8],
        )
    
    logger.debug(
        "Building invoice snapshot: auth_user_id=%s bill_to_name=%s bill_to_email=%s",
        str(auth_user_id)[:8] + "...",
        bill_to.get("name"),
        bill_to.get("billing_email") or bill_to.get("email"),
    )
    
    snapshot = {
        "version": "1.0",
        "issuer": ISSUER_INFO,
        "receipt_from": RECEIPT_FROM,
        "bill_to": bill_to,
        "line_items": _build_line_items(
            package_id=intent.package_id,
            package_name=package_name,
            credits_amount=intent.credits_amount,
            price_cents=intent.price_cents,
            currency=intent.currency,
        ),
        "totals": _build_totals(
            price_cents=intent.price_cents,
            currency=intent.currency,
        ),
        "payment_details": _build_payment_details(intent),
        "notes": {
            "disclaimer": "Este documento es un recibo comercial y no constituye una factura fiscal (CFDI).",
            "terms": "Los créditos no son reembolsables ni transferibles.",
        },
    }
    
    try:
        # Crear invoice con placeholder para invoice_number
        # Usamos un placeholder único temporal basado en intent_id
        placeholder_number = f"TEMP-{intent.id}"
        
        invoice = BillingInvoice(
            checkout_intent_id=intent.id,
            auth_user_id=auth_user_id,  # SSOT: UUID
            invoice_number=placeholder_number,
            snapshot_json=snapshot,
            issued_at=now,
            paid_at=paid_at,
        )
        
        session.add(invoice)
        await session.flush()  # Obtener invoice.id
        
        # Generar invoice_number basado en ID (concurrency-safe)
        invoice_number = _generate_invoice_number(year, invoice.id)
        invoice.invoice_number = invoice_number
        
        # Actualizar snapshot con invoice_number correcto
        snapshot["invoice_number"] = invoice_number
        invoice.snapshot_json = snapshot
        
        await session.commit()
        await session.refresh(invoice)
        
        logger.info(
            "Created invoice: number=%s intent=%s auth_user_id=%s",
            invoice_number, intent.id, str(auth_user_id)[:8] + "...",
        )
        
        return invoice
        
    except IntegrityError:
        # Race condition: otro proceso creó el invoice primero
        # Rollback y obtener el existente
        await session.rollback()
        
        result = await session.execute(
            select(BillingInvoice).where(
                BillingInvoice.checkout_intent_id == intent.id
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.debug("Invoice created by concurrent request: intent=%s", intent.id)
            return existing
        
        # Si aún no existe, re-lanzar el error
        raise


async def get_invoice_by_intent_id(
    session: AsyncSession,
    intent_id: int,
) -> Optional[BillingInvoice]:
    """Obtiene invoice por checkout_intent_id."""
    result = await session.execute(
        select(BillingInvoice).where(
            BillingInvoice.checkout_intent_id == intent_id
        )
    )
    return result.scalar_one_or_none()


__all__ = [
    "get_or_create_invoice",
    "get_invoice_by_intent_id",
    "ISSUER_INFO",
    "RECEIPT_FROM",
]
