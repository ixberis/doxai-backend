# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/services/purchase_email_service.py

Servicio para envío de emails de confirmación de compra.

Responsabilidades:
- Generar tokens públicos para recibos
- Construir contexto de email
- Enviar email via EmailSender
- Marcar invoice como email_sent (idempotencia)

Autor: DoxAI
Fecha: 2026-01-01
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ..models_invoice import BillingInvoice
from ..models import CheckoutIntent
from ..credit_packages import get_package_by_id

if TYPE_CHECKING:
    from app.shared.integrations.email_sender import IEmailSender

logger = logging.getLogger(__name__)

# TTL por defecto para tokens públicos (7 días = 168 horas)
DEFAULT_PUBLIC_TOKEN_TTL_HOURS = 168


def get_public_token_ttl_hours() -> int:
    """Obtiene el TTL de tokens públicos desde env."""
    try:
        return int(os.getenv("BILLING_RECEIPT_PUBLIC_TTL_HOURS", DEFAULT_PUBLIC_TOKEN_TTL_HOURS))
    except ValueError:
        return DEFAULT_PUBLIC_TOKEN_TTL_HOURS


def get_app_public_base_url() -> str:
    """Obtiene la URL pública de la aplicación."""
    return os.getenv("APP_PUBLIC_BASE_URL", os.getenv("FRONTEND_URL", "https://app.doxai.site"))


def generate_public_token() -> str:
    """
    Genera un token público URL-safe para recibos.
    
    Returns:
        Token de 48 caracteres URL-safe (32 bytes en base64url).
    """
    return secrets.token_urlsafe(32)


async def ensure_public_token(
    session: AsyncSession,
    invoice: BillingInvoice,
) -> str:
    """
    Asegura que el invoice tenga un token público válido.
    
    Si no tiene token o está expirado, genera uno nuevo.
    
    Args:
        session: Sesión de base de datos
        invoice: Invoice a procesar
        
    Returns:
        Token público válido
    """
    now = datetime.now(timezone.utc)
    ttl_hours = get_public_token_ttl_hours()
    
    # Verificar si necesita nuevo token
    needs_new_token = (
        not invoice.public_token or
        (invoice.public_token_expires_at and invoice.public_token_expires_at <= now)
    )
    
    if needs_new_token:
        invoice.public_token = generate_public_token()
        invoice.public_token_expires_at = now + timedelta(hours=ttl_hours)
        await session.commit()
        await session.refresh(invoice)
        
        logger.info(
            "Generated new public token for invoice: invoice=%s expires=%s",
            invoice.invoice_number,
            invoice.public_token_expires_at,
        )
    
    return invoice.public_token


def build_receipt_urls(token: str, intent_id: Optional[int] = None) -> Dict[str, str]:
    """
    Construye URLs públicas para el recibo.
    
    Args:
        token: Token público del invoice
        intent_id: ID del checkout intent (ignorado, se mantiene por compatibilidad)
        
    Returns:
        Dict con view_url, pdf_url y json_url
    """
    base_url = get_app_public_base_url().rstrip("/")
    
    # view_url siempre apunta a la página de recibos
    view_url = f"{base_url}/billing/receipts"
    
    return {
        "view_url": view_url,
        "pdf_url": f"{base_url}/api/billing/receipts/public/{token}.pdf",
        "json_url": f"{base_url}/api/billing/receipts/public/{token}.json",
    }


def _format_price(cents: int, currency: str) -> str:
    """Formatea precio de centavos a string legible."""
    amount = cents / 100
    symbol = "$" if currency.upper() in ("MXN", "USD") else ""
    return f"{symbol}{amount:,.2f} {currency.upper()}"


def _format_datetime(dt: Optional[datetime]) -> str:
    """Formatea datetime para email."""
    if not dt:
        return "N/A"
    return dt.strftime("%d/%m/%Y %H:%M UTC")


def build_email_context(
    invoice: BillingInvoice,
    intent: CheckoutIntent,
    user_name: Optional[str] = None,
    user_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construye el contexto para el template de email de compra.
    
    Args:
        invoice: Invoice con snapshot
        intent: CheckoutIntent de la compra
        user_name: Nombre del usuario
        user_email: Email del usuario
        
    Returns:
        Dict con todas las variables para el template
    """
    # Obtener nombre del paquete
    package = get_package_by_id(intent.package_id)
    package_name = package.name if package else f"Paquete de créditos ({intent.package_id})"
    
    # URLs de recibo (con intent_id para view_url real)
    receipt_urls = build_receipt_urls(invoice.public_token, intent.id) if invoice.public_token else {}
    
    # Nombre para saludo
    display_name = user_name or "Usuario"
    snap = invoice.snapshot_json or {}
    bill_to = snap.get("bill_to", {})
    if bill_to.get("name") and not bill_to["name"].startswith("Usuario #"):
        display_name = bill_to["name"]
    
    return {
        # Usuario
        "user_name": display_name,
        "user_email": user_email or "",
        
        # Compra
        "package_name": package_name,
        "credits_amount": intent.credits_amount,
        "amount": _format_price(intent.price_cents, intent.currency),
        "amount_raw": intent.price_cents / 100,
        "currency": intent.currency.upper(),
        
        # Transacción
        "intent_id": intent.id,
        "invoice_number": invoice.invoice_number,
        "transaction_id": f"DXI-{intent.id:06d}",
        "payment_date": _format_datetime(invoice.paid_at or invoice.issued_at),
        "provider": (intent.provider or "stripe").upper(),
        
        # URLs
        "receipt_view_url": receipt_urls.get("view_url", ""),
        "receipt_pdf_url": receipt_urls.get("pdf_url", ""),
        "receipt_json_url": receipt_urls.get("json_url", ""),
        "frontend_url": get_app_public_base_url(),
        
        # Metadata
        "current_year": datetime.now(timezone.utc).year,
    }


async def send_purchase_confirmation_email(
    session: AsyncSession,
    invoice: BillingInvoice,
    intent: CheckoutIntent,
    user_email: str,
    user_name: Optional[str] = None,
    email_sender: Optional["IEmailSender"] = None,
) -> bool:
    """
    Envía email de confirmación de compra.
    
    Idempotente: no reenvía si ya se envió (purchase_email_sent_at).
    Best-effort: errores de email se loguean pero no se propagan.
    
    Args:
        session: Sesión de base de datos
        invoice: Invoice de la compra
        intent: CheckoutIntent
        user_email: Email destino
        user_name: Nombre del usuario (opcional)
        email_sender: Sender a usar (opcional, carga de settings si no se provee)
        
    Returns:
        True si se envió, False si ya estaba enviado o falló
    """
    # Idempotencia: verificar si ya se envió
    if invoice.purchase_email_sent_at:
        logger.info(
            "Purchase email already sent: invoice=%s sent_at=%s",
            invoice.invoice_number,
            invoice.purchase_email_sent_at,
        )
        return False
    
    try:
        # Asegurar que tenga token público
        await ensure_public_token(session, invoice)
        
        # Obtener email sender
        if email_sender is None:
            from app.shared.integrations.email_sender import get_email_sender
            email_sender = get_email_sender()
        
        # Construir contexto
        context = build_email_context(invoice, intent, user_name, user_email)
        
        # Construir cuerpo del email
        from app.shared.integrations.email_templates import render_email
        
        html, text, used_template = render_email("purchase_confirmation_email", context)
        
        if not text:
            text = _build_fallback_text(context)
        if not html:
            import html as html_lib
            html = f"<pre>{html_lib.escape(text)}</pre>"
        
        # Enviar email
        await email_sender._send_email(
            to_email=user_email,
            subject="Confirmación de compra de créditos — DoxAI",
            html_body=html,
            text_body=text,
        )
        
        # Marcar como enviado
        invoice.purchase_email_sent_at = datetime.now(timezone.utc)
        await session.commit()
        
        logger.info(
            "purchase_confirmation_email_sent: invoice=%s to=%s intent=%s",
            invoice.invoice_number,
            user_email[:3] + "***" if user_email else "unknown",
            intent.id,
        )
        
        return True
        
    except Exception as e:
        # Best-effort: loguear error pero no propagar
        logger.error(
            "purchase_confirmation_email_failed: invoice=%s to=%s error=%s",
            invoice.invoice_number,
            user_email[:3] + "***" if user_email else "unknown",
            str(e),
        )
        return False


def _build_fallback_text(context: Dict[str, Any]) -> str:
    """Construye texto plano de fallback para el email."""
    return f"""Estimado/a {context['user_name']},

¡Gracias por tu compra en DoxAI!

Tu pago ha sido procesado exitosamente.

=== RESUMEN DE COMPRA ===
Paquete: {context['package_name']}
Créditos: {context['credits_amount']}
Monto: {context['amount']}
Fecha: {context['payment_date']}
ID de transacción: {context['transaction_id']}

=== RECIBO ===
Ver recibo: {context['receipt_view_url']}
Descargar PDF: {context['receipt_pdf_url']}

Nota: Este es un recibo comercial, no un CFDI.

Gracias por elegir DoxAI.

Atentamente,
El equipo de DoxAI
"""


__all__ = [
    "generate_public_token",
    "ensure_public_token",
    "build_receipt_urls",
    "build_email_context",
    "send_purchase_confirmation_email",
    "get_public_token_ttl_hours",
    "get_app_public_base_url",
]
