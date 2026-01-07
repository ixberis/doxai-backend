# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/admin/operation/event_logger.py

Logger de eventos operativos de Billing.

Proporciona métodos para registrar eventos estructurados
en billing_operation_events.

IMPORTANTE:
- Los eventos se insertan en una SESIÓN INDEPENDIENTE para no contaminar
  la transacción principal del request.
- Fire-and-forget: errores se loguean pero no propagan.
- Si falla el logging, el request principal continúa sin afectarse.

Uso:
    event_logger = BillingOperationEventLogger()
    await event_logger.log_public_pdf_access(invoice_id=123)
    await event_logger.log_token_expired(invoice_id=123)
    await event_logger.log_email_sent(invoice_id=123, intent_id=456)

Autor: DoxAI
Fecha: 2026-01-02
Updated: 2026-01-07 - Sesión independiente para no romper transacciones principales
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional, TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


logger = logging.getLogger(__name__)

# Flag to log factory warning only once per process
_factory_warning_logged = False


class BillingOperationEventName(str, Enum):
    """
    Eventos operativos válidos para billing_operation_events.
    
    Debe coincidir con billing_operation_event_name_enum en PostgreSQL.
    """
    # Recibos públicos
    PUBLIC_PDF_ACCESS = "billing.receipt.public_pdf_access"
    PUBLIC_JSON_ACCESS = "billing.receipt.public_json_access"
    TOKEN_EXPIRED = "billing.receipt.token_expired"
    TOKEN_NOT_FOUND = "billing.receipt.token_not_found"
    
    # Emails
    EMAIL_SENT = "billing.email.sent"
    EMAIL_FAILED = "billing.email.failed"
    
    # PDF
    PDF_GENERATION_FAILED = "billing.pdf.generation_failed"
    
    # Errores HTTP
    HTTP_4XX_ERROR = "billing.error.4xx"
    HTTP_5XX_ERROR = "billing.error.5xx"


class BillingOperationEventCategory(str, Enum):
    """
    Categorías de eventos operativos.
    
    Debe coincidir con billing_operation_event_category_enum en PostgreSQL.
    """
    RECEIPT = "receipt"
    EMAIL = "email"
    PDF = "pdf"
    ERROR = "error"


def _get_session_factory() -> Optional["async_sessionmaker[AsyncSession]"]:
    """
    Get SessionLocal from canonical database module.
    
    Returns None if unavailable (with warning logged once).
    """
    global _factory_warning_logged
    
    try:
        from app.shared.database.database import SessionLocal
        return SessionLocal
    except ImportError as e:
        if not _factory_warning_logged:
            logger.warning(
                "billing_operation_event_log_disabled: SessionLocal import failed: %s",
                str(e)
            )
            _factory_warning_logged = True
        return None


class BillingOperationEventLogger:
    """
    Logger de eventos operativos para billing_operation_events.
    
    Todos los métodos son fire-and-forget con manejo de errores interno.
    No propagan excepciones para evitar afectar el flujo principal.
    
    IMPORTANTE: Usa sesión INDEPENDIENTE para no contaminar la transacción
    del request principal. Esto evita PendingRollbackError en webhooks.
    """
    
    def __init__(self, session: Optional["AsyncSession"] = None):
        """
        Initialize logger.
        
        Args:
            session: Legacy parameter, ignored. Uses SessionLocal internally
                     for isolated transactions.
        """
        # session parameter kept for backwards compatibility but ignored
        pass
    
    async def _log_event(
        self,
        event_name: BillingOperationEventName,
        event_category: BillingOperationEventCategory,
        success: bool = True,
        error_code: Optional[str] = None,
        invoice_id: Optional[int] = None,
        intent_id: Optional[int] = None,
        request_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Inserta un evento en billing_operation_events usando sesión independiente.
        
        Fire-and-forget: errores se loguean pero no se propagan.
        Usa sesión aislada para no contaminar la transacción del request.
        """
        session_factory = _get_session_factory()
        if session_factory is None:
            # Warning already logged once
            return
        
        try:
            async with session_factory() as log_session:
                # Use CAST() instead of :: to avoid asyncpg placeholder issues
                query = text("""
                    INSERT INTO public.billing_operation_events (
                        event_name, event_category, success, error_code,
                        invoice_id, intent_id, request_id, user_agent
                    ) VALUES (
                        CAST(:event_name AS public.billing_operation_event_name_enum),
                        CAST(:event_category AS public.billing_operation_event_category_enum),
                        :success, :error_code,
                        :invoice_id, :intent_id, :request_id, :user_agent
                    )
                """)
                
                await log_session.execute(query, {
                    "event_name": event_name.value,
                    "event_category": event_category.value,
                    "success": success,
                    "error_code": error_code,
                    "invoice_id": invoice_id,
                    "intent_id": intent_id,
                    "request_id": request_id,
                    "user_agent": user_agent[:255] if user_agent else None,
                })
                
                # Commit in the isolated session
                await log_session.commit()
            
            logger.debug(
                "billing_operation_event_logged: %s success=%s",
                event_name.value, success
            )
            
        except Exception as e:
            # Fire-and-forget: no propagar, pero loguear con stacktrace completo
            logger.exception(
                "billing_operation_event_log_failed: %s error=%s",
                event_name.value if hasattr(event_name, 'value') else event_name,
                str(e)
            )
    
    # ─────────────────────────────────────────────────────────────
    # Eventos de recibos públicos
    # ─────────────────────────────────────────────────────────────
    
    async def log_public_pdf_access(
        self,
        invoice_id: Optional[int] = None,
        request_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Registra acceso exitoso a PDF público."""
        await self._log_event(
            event_name=BillingOperationEventName.PUBLIC_PDF_ACCESS,
            event_category=BillingOperationEventCategory.RECEIPT,
            success=True,
            invoice_id=invoice_id,
            request_id=request_id,
            user_agent=user_agent,
        )
    
    async def log_public_json_access(
        self,
        invoice_id: Optional[int] = None,
        request_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Registra acceso exitoso a JSON público."""
        await self._log_event(
            event_name=BillingOperationEventName.PUBLIC_JSON_ACCESS,
            event_category=BillingOperationEventCategory.RECEIPT,
            success=True,
            invoice_id=invoice_id,
            request_id=request_id,
            user_agent=user_agent,
        )
    
    async def log_token_expired(
        self,
        invoice_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """Registra intento de acceso con token expirado."""
        await self._log_event(
            event_name=BillingOperationEventName.TOKEN_EXPIRED,
            event_category=BillingOperationEventCategory.RECEIPT,
            success=False,
            error_code="token_expired",
            invoice_id=invoice_id,
            request_id=request_id,
        )
    
    async def log_token_not_found(
        self,
        request_id: Optional[str] = None,
    ) -> None:
        """Registra intento de acceso con token inexistente."""
        await self._log_event(
            event_name=BillingOperationEventName.TOKEN_NOT_FOUND,
            event_category=BillingOperationEventCategory.RECEIPT,
            success=False,
            error_code="token_not_found",
            request_id=request_id,
        )
    
    # ─────────────────────────────────────────────────────────────
    # Eventos de emails
    # ─────────────────────────────────────────────────────────────
    
    async def log_email_sent(
        self,
        invoice_id: Optional[int] = None,
        intent_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """Registra email de compra enviado exitosamente."""
        await self._log_event(
            event_name=BillingOperationEventName.EMAIL_SENT,
            event_category=BillingOperationEventCategory.EMAIL,
            success=True,
            invoice_id=invoice_id,
            intent_id=intent_id,
            request_id=request_id,
        )
    
    async def log_email_failed(
        self,
        invoice_id: Optional[int] = None,
        intent_id: Optional[int] = None,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """Registra email de compra fallido."""
        await self._log_event(
            event_name=BillingOperationEventName.EMAIL_FAILED,
            event_category=BillingOperationEventCategory.EMAIL,
            success=False,
            error_code=error_code or "email_send_failed",
            invoice_id=invoice_id,
            intent_id=intent_id,
            request_id=request_id,
        )
    
    # ─────────────────────────────────────────────────────────────
    # Eventos de PDF
    # ─────────────────────────────────────────────────────────────
    
    async def log_pdf_generation_failed(
        self,
        invoice_id: Optional[int] = None,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """Registra fallo en generación de PDF."""
        await self._log_event(
            event_name=BillingOperationEventName.PDF_GENERATION_FAILED,
            event_category=BillingOperationEventCategory.PDF,
            success=False,
            error_code=error_code or "pdf_generation_failed",
            invoice_id=invoice_id,
            request_id=request_id,
        )
    
    # ─────────────────────────────────────────────────────────────
    # Eventos de errores HTTP
    # ─────────────────────────────────────────────────────────────
    
    async def log_http_4xx_error(
        self,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """Registra error HTTP 4xx (cliente)."""
        await self._log_event(
            event_name=BillingOperationEventName.HTTP_4XX_ERROR,
            event_category=BillingOperationEventCategory.ERROR,
            success=False,
            error_code=error_code,
            request_id=request_id,
        )
    
    async def log_http_5xx_error(
        self,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """Registra error HTTP 5xx (servidor)."""
        await self._log_event(
            event_name=BillingOperationEventName.HTTP_5XX_ERROR,
            event_category=BillingOperationEventCategory.ERROR,
            success=False,
            error_code=error_code,
            request_id=request_id,
        )


__all__ = [
    "BillingOperationEventLogger",
    "BillingOperationEventName",
    "BillingOperationEventCategory",
]
