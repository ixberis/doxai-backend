# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/services/purchase_email_service.py

Servicio para envío de emails de confirmación de compra.

Responsabilidades:
- Generar tokens públicos para recibos
- Construir contexto de email
- Enviar email via MailerSend con instrumentación en auth_email_events
- Marcar invoice como email_sent (idempotencia)
- Loguear eventos operativos (billing.email.sent / billing.email.failed)

DB 2.0 SSOT:
- Los eventos de email se registran en auth_email_events con email_type='purchase_confirmation'
- Usa auth_user_id (UUID) para tracking
- correlation_id se genera automáticamente si no viene

Autor: DoxAI
Fecha: 2026-01-01
Actualizado: 2026-01-13 - Instrumentación completa en auth_email_events
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..models_invoice import BillingInvoice
from ..models import CheckoutIntent
from ..credit_packages import get_package_by_id
from ..admin.operation.event_logger import BillingOperationEventLogger

if TYPE_CHECKING:
    from app.shared.integrations.email_sender import IEmailSender
    from sqlalchemy.ext.asyncio import async_sessionmaker

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


def _classify_email_error(error: Exception) -> str:
    """
    Clasifica el error de email en un código estandarizado.
    
    Args:
        error: Excepción capturada
        
    Returns:
        Código de error estandarizado
    """
    error_str = str(error).lower()
    
    if "template" in error_str:
        return "template_missing"
    elif "smtp" in error_str or "connection" in error_str:
        return "provider_error"
    elif "timeout" in error_str:
        return "provider_timeout"
    elif "rate" in error_str or "limit" in error_str:
        return "rate_limited"
    elif "invalid" in error_str and "email" in error_str:
        return "invalid_email"
    else:
        return "email_send_failed"


async def send_purchase_confirmation_email(
    session: AsyncSession,
    invoice: BillingInvoice,
    intent: CheckoutIntent,
    user_email: str,
    user_name: Optional[str] = None,
    email_sender: Optional["IEmailSender"] = None,
    auth_user_id: Optional[UUID] = None,
) -> bool:
    """
    Envía email de confirmación de compra con instrumentación en auth_email_events.
    
    Idempotente: no reenvía si ya se envió (purchase_email_sent_at).
    Best-effort: errores de email se loguean pero no se propagan.
    
    DB 2.0 SSOT:
    - Registra evento en auth_email_events con email_type='purchase_confirmation'
    - Usa auth_user_id (UUID) para tracking
    - correlation_id autogenerado si no viene
    
    IMPORTANTE: Usa método PÚBLICO send_purchase_confirmation_email del sender
    para garantizar instrumentación completa (NO usa _send_email privado).
    
    Args:
        session: Sesión de base de datos
        invoice: Invoice de la compra
        intent: CheckoutIntent
        user_email: Email destino
        user_name: Nombre del usuario (opcional)
        email_sender: Sender a usar (opcional, carga de settings si no se provee)
        auth_user_id: UUID del usuario (SSOT, se obtiene de intent si no se provee)
        
    Returns:
        True si se envió, False si ya estaba enviado o falló
    """
    event_logger = BillingOperationEventLogger(session)
    email_type = "purchase_confirmation"
    
    # SSOT: obtener auth_user_id de intent si no se provee
    if auth_user_id is None:
        auth_user_id = getattr(intent, "auth_user_id", None)
    
    # Generar correlation_id único para esta transacción
    correlation_id = f"email:{email_type}:{uuid4().hex}"
    
    # Generar idempotency_key estable basado en invoice
    idem_ctx = f"inv:{invoice.id}:{intent.id}"
    idem_raw = f"{email_type}:{str(auth_user_id) if auth_user_id else 'no_auth'}:{idem_ctx}"
    idempotency_key = hashlib.sha256(idem_raw.encode()).hexdigest()[:64]
    
    # Idempotencia: verificar si ya se envió
    if invoice.purchase_email_sent_at:
        logger.info(
            "purchase_confirmation_email_already_sent: invoice=%s sent_at=%s",
            invoice.invoice_number,
            invoice.purchase_email_sent_at,
        )
        return False
    
    # Obtener email sender (MailerSend en producción)
    if email_sender is None:
        from app.shared.integrations.email_sender import get_email_sender
        email_sender = get_email_sender()
    
    try:
        # Asegurar que tenga token público
        await ensure_public_token(session, invoice)
        
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
        
        # ─────────────────────────────────────────────────────────────────
        # Enviar via método PÚBLICO del sender (instrumentación incluida)
        # El sender maneja: pending → send → sent/failed
        # ─────────────────────────────────────────────────────────────────
        message_id = await email_sender.send_purchase_confirmation_email(
            to_email=user_email,
            subject="Confirmación de compra de créditos — DoxAI",
            html_body=html,
            text_body=text,
            auth_user_id=auth_user_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        
        # Marcar invoice como enviado
        invoice.purchase_email_sent_at = datetime.now(timezone.utc)
        
        # Log evento operativo legacy (fire-and-forget)
        await event_logger.log_email_sent(
            invoice_id=invoice.id,
            intent_id=intent.id,
        )
        
        await session.commit()
        
        logger.info(
            "purchase_confirmation_email_sent: invoice=%s to=%s intent=%s provider_message_id=%s correlation_id=%s auth_user_id=%s",
            invoice.invoice_number,
            user_email[:3] + "***" if user_email else "unknown",
            intent.id,
            message_id,
            correlation_id,
            (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
        )
        
        return True
        
    except Exception as e:
        error_code = _classify_email_error(e)
        
        # Log evento operativo legacy (fire-and-forget)
        try:
            await event_logger.log_email_failed(
                invoice_id=invoice.id,
                intent_id=intent.id,
                error_code=error_code,
            )
            await session.commit()
        except Exception:
            pass
        
        logger.error(
            "purchase_confirmation_email_failed: invoice=%s to=%s error=%s error_code=%s correlation_id=%s",
            invoice.invoice_number,
            user_email[:3] + "***" if user_email else "unknown",
            str(e),
            error_code,
            correlation_id,
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
