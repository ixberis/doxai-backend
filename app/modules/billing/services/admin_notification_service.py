# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/services/admin_notification_service.py

Servicio para enviar notificaciones al admin cuando se realiza una compra.

Características:
- Idempotente: usa admin_notify_sent_at en billing_invoices
- Best-effort: errores no bloquean la compra
- Configurable via BILLING_ADMIN_NOTIFY_EMAIL
- NO hace commit/rollback (responsabilidad del caller)

IMPORTANTE: Este service solo hace flush(), el caller hace commit().

Autor: DoxAI
Fecha: 2026-01-15
Updated: 2026-01-15 - P0 fixes: no commit, API pública
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ..models_invoice import BillingInvoice
from ..models import CheckoutIntent
from ..credit_packages import get_package_by_id
from .purchase_email_service import (
    build_receipt_urls,
    get_app_public_base_url,
)

if TYPE_CHECKING:
    from app.shared.integrations.mailersend_email_sender import MailerSendEmailSender

logger = logging.getLogger(__name__)

# Constantes
EMAIL_TYPE = "admin_purchase_notification"


def get_admin_notify_email() -> Optional[str]:
    """
    Obtiene el email del admin para notificaciones.
    
    Returns:
        Email del admin o None si no está configurado.
    """
    email = os.getenv("BILLING_ADMIN_NOTIFY_EMAIL", "").strip()
    return email if email else None


def _format_price(cents: int, currency: str) -> str:
    """Formatea precio de centavos a string legible."""
    amount = cents / 100
    symbol = "$" if currency.upper() in ("MXN", "USD") else ""
    return f"{symbol}{amount:,.2f} {currency.upper()}"


def _format_datetime(dt: Optional[datetime]) -> str:
    """Formatea datetime para email."""
    if not dt:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def build_admin_email_context(
    invoice: BillingInvoice,
    intent: CheckoutIntent,
    payment_id: Union[int, str],
    customer_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Construye el contexto para el template de email de notificación al admin.
    
    Args:
        invoice: Invoice de la compra
        intent: CheckoutIntent de la compra
        payment_id: ID del payment creado (int o "N/A" si no existe)
        customer_email: Email del cliente
        
    Returns:
        Dict con todas las variables para el template
    """
    # Obtener nombre del paquete
    package = get_package_by_id(intent.package_id)
    package_name = package.name if package else f"Paquete ({intent.package_id})"
    
    # Construir link del recibo público
    receipt_link = "Token no disponible"
    if invoice.public_token and invoice.is_public_token_valid():
        urls = build_receipt_urls(invoice.public_token)
        receipt_link = urls.get("pdf_url", receipt_link)
    
    return {
        # Compra
        "package_name": package_name,
        "credits_amount": intent.credits_amount,
        "amount": _format_price(intent.price_cents, intent.currency),
        "provider": (intent.provider or "stripe").upper(),
        
        # Cliente
        "customer_email": customer_email or "No disponible",
        "auth_user_id": str(intent.auth_user_id),
        
        # Transacción
        "invoice_number": invoice.invoice_number or "N/A",
        "payment_id": payment_id,
        "intent_id": intent.id,
        "provider_session_id": intent.provider_session_id or "N/A",
        "transaction_datetime": _format_datetime(intent.completed_at or datetime.now(timezone.utc)),
        "receipt_link": receipt_link,
        
        # Metadata
        "current_year": datetime.now(timezone.utc).year,
    }


def _build_fallback_text(context: Dict[str, Any]) -> str:
    """Construye texto plano de fallback para el email."""
    return f"""=== NUEVA COMPRA DE CRÉDITOS - DoxAI ===

Paquete: {context['package_name']}
Créditos: {context['credits_amount']}
Monto: {context['amount']}
Proveedor: {context['provider']}

Cliente: {context['customer_email']}
auth_user_id: {context['auth_user_id']}

Invoice #: {context['invoice_number']}
Payment ID: {context['payment_id']}
Intent ID: {context['intent_id']}
Fecha: {context['transaction_datetime']}

---
Notificación automática de DoxAI
"""


async def send_admin_purchase_notification(
    session: AsyncSession,
    invoice: BillingInvoice,
    intent: CheckoutIntent,
    payment_id: Union[int, str, None] = None,
    customer_email: Optional[str] = None,
    email_sender: Optional["MailerSendEmailSender"] = None,
    dry_run: bool = False,
) -> bool:
    """
    Envía notificación al admin sobre una compra completada.
    
    Características:
    - Idempotente: verifica admin_notify_sent_at antes de enviar
    - Best-effort: errores se loguean pero NO se propagan
    - Configurable: requiere BILLING_ADMIN_NOTIFY_EMAIL
    - NO hace commit (caller responsable)
    
    IMPORTANTE:
    - Si envío falla, NO setea admin_notify_sent_at
    - Solo setea admin_notify_sent_at + flush() si envío es exitoso
    - Caller debe hacer commit() después
    
    Args:
        session: Sesión de base de datos
        invoice: Invoice de la compra
        intent: CheckoutIntent
        payment_id: ID del payment creado (o None/"N/A")
        customer_email: Email del cliente (para contexto)
        email_sender: Sender a usar (opcional)
        dry_run: Si es True, no envía email (para backfill dry-run)
        
    Returns:
        True si se envió, False si se omitió o falló
    """
    admin_email = get_admin_notify_email()
    correlation_id = f"admin_notify:{invoice.id}:{uuid4().hex[:8]}"
    
    # Resolver payment_id para display
    display_payment_id: Union[int, str] = payment_id if payment_id else "N/A"
    
    # Skip si no hay email de admin configurado
    if not admin_email:
        logger.info(
            "admin_purchase_notify_skipped: reason=no_admin_email "
            "invoice=%s intent=%s",
            invoice.invoice_number,
            intent.id,
        )
        return False
    
    # Idempotencia: verificar si ya se envió
    if invoice.admin_notify_sent_at:
        logger.info(
            "admin_purchase_notify_skipped: reason=already_sent "
            "invoice=%s sent_at=%s",
            invoice.invoice_number,
            invoice.admin_notify_sent_at,
        )
        return False
    
    # Skip en dry_run
    if dry_run:
        logger.info(
            "admin_purchase_notify_skipped: reason=dry_run "
            "invoice=%s intent=%s",
            invoice.invoice_number,
            intent.id,
        )
        return False
    
    logger.info(
        "admin_purchase_notify_started: invoice=%s intent=%s "
        "payment_id=%s to=%s correlation_id=%s",
        invoice.invoice_number,
        intent.id,
        display_payment_id,
        admin_email[:3] + "***",
        correlation_id,
    )
    
    # Obtener email sender
    if email_sender is None:
        from app.shared.integrations.email_sender import get_email_sender
        email_sender = get_email_sender()  # type: ignore[assignment]
    
    try:
        # Construir contexto
        context = build_admin_email_context(
            invoice=invoice,
            intent=intent,
            payment_id=display_payment_id,
            customer_email=customer_email,
        )
        
        # Renderizar template
        from app.shared.integrations.email_templates import render_email
        
        html, text, used_template = render_email(
            "admin_purchase_notification_email",
            context,
        )
        
        if not text:
            text = _build_fallback_text(context)
        if not html:
            import html as html_lib
            html = f"<pre>{html_lib.escape(text)}</pre>"
        
        # Generar idempotency_key estable basado en invoice.id
        # (invoice.id es único por compra, más estable que payment_id que puede no existir)
        idem_raw = f"admin_purchase_notification:{invoice.id}"
        idempotency_key = hashlib.sha256(idem_raw.encode()).hexdigest()[:64]
        
        subject = f"[DoxAI] Nueva compra: {context['amount']} - {invoice.invoice_number}"
        
        # ─────────────────────────────────────────────────────────────────
        # Enviar via API PÚBLICA: send_internal_email
        # - NO inserta en auth_email_events (email interno admin)
        # - NO requiere email_type en enum SQL
        # - Best-effort: caller atrapa excepción
        # ─────────────────────────────────────────────────────────────────
        
        message_id = await email_sender.send_internal_email(
            to_email=admin_email,
            subject=subject,
            html_body=html,
            text_body=text,
        )
        
        # Marcar como enviado (idempotencia) - solo flush, NO commit
        invoice.admin_notify_sent_at = datetime.now(timezone.utc)
        await session.flush()
        
        logger.info(
            "admin_purchase_notify_sent: invoice=%s intent=%s "
            "payment_id=%s to=%s correlation_id=%s message_id=%s",
            invoice.invoice_number,
            intent.id,
            display_payment_id,
            admin_email[:3] + "***",
            correlation_id,
            message_id,
        )
        
        return True
        
    except Exception as e:
        # Best-effort: log error pero NO propagar excepción
        # IMPORTANTE: NO setear admin_notify_sent_at si falla
        logger.error(
            "admin_purchase_notify_failed: invoice=%s intent=%s "
            "payment_id=%s error=%s correlation_id=%s",
            invoice.invoice_number,
            intent.id,
            display_payment_id,
            str(e),
            correlation_id,
        )
        return False


__all__ = [
    "send_admin_purchase_notification",
    "get_admin_notify_email",
    "build_admin_email_context",
]
