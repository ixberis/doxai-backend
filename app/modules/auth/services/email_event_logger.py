# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/email_event_logger.py

Servicio para registrar eventos de envío de emails en auth_email_events.
Diseñado para instrumentación de MailerSendEmailSender y otros providers.

IMPORTANTE: Usa sesión separada para commits, aislando del ciclo transaccional
del request principal. Esto garantiza que los logs no se pierdan en rollback.

Autor: Sistema
Fecha: 2026-01-02
Updated: 2026-01-04 - Sesión separada para commits (igual que MailerSendEmailSender)
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Literal, TYPE_CHECKING
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

# Flag to log factory validation warning only once per process
_factory_warning_logged = False

# Canonical import path for SessionLocal (source of truth)
_SESSIONLOCAL_IMPORT_PATH = "app.shared.database.database"

# Tipos de email soportados
EmailType = Literal[
    "account_activation",
    "account_created", 
    "password_reset_request",
    "password_reset_success",
    "welcome"
]

# Status de evento
EventStatus = Literal["pending", "sent", "failed"]


@dataclass
class EmailEventData:
    """Datos para registrar un evento de email."""
    email_type: EmailType
    status: EventStatus
    recipient_domain: Optional[str] = None
    user_id: Optional[int] = None
    provider: str = "mailersend"
    provider_message_id: Optional[str] = None
    latency_ms: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    idempotency_key: Optional[str] = None
    correlation_id: Optional[str] = None


class EmailEventLogger:
    """
    Registra eventos de envío de email para métricas.
    
    IMPORTANTE: Usa sesión separada (vía async_sessionmaker) para commits.
    No interfiere con la transacción del request principal.
    
    Uso típico:
    1. Antes de enviar: log_event(status='pending')
    2. Después de éxito: update_event(status='sent', latency_ms=...)
    3. Si falla: update_event(status='failed', error_code=...)
    
    O en modo simplificado:
    - log_event(status='sent', latency_ms=...) directamente después de envío exitoso
    """
    
    def __init__(
        self,
        db: AsyncSession = None,
        event_session_factory: Optional["async_sessionmaker[AsyncSession]"] = None,
    ):
        """
        Args:
            db: Sesión de referencia (legacy, se ignora).
            event_session_factory: async_sessionmaker para crear sesiones de logging.
                Si no se provee, usa SessionLocal de database.py.
        """
        self.db = db  # Kept for backwards compatibility
        self._event_session_factory = event_session_factory
    
    def _get_event_session_factory(self) -> Optional["async_sessionmaker[AsyncSession]"]:
        """
        Get the session factory for event logging with validation.
        
        Priority:
        1. Injected event_session_factory (validated)
        2. SessionLocal from canonical database module
        3. None (logging disabled with clear warning)
        
        Returns:
            Valid async_sessionmaker or None if unavailable/invalid.
        """
        global _factory_warning_logged
        
        # 1. Check injected factory
        if self._event_session_factory is not None:
            # Validate it's callable
            if not callable(self._event_session_factory):
                if not _factory_warning_logged:
                    logger.warning(
                        "email_event_log_skipped_invalid_factory: "
                        "event_session_factory is not callable"
                    )
                    _factory_warning_logged = True
                return None
            return self._event_session_factory
        
        # 2. Fallback to canonical SessionLocal import
        try:
            from app.shared.database.database import SessionLocal
            return SessionLocal
        except ImportError as e:
            if not _factory_warning_logged:
                logger.warning(
                    "email_event_log_skipped_no_sessionlocal_import: %s",
                    str(e)
                )
                _factory_warning_logged = True
            return None
    
    @staticmethod
    def extract_domain(email: str) -> Optional[str]:
        """
        Extrae el dominio de un email (sin PII).
        
        Args:
            email: Email completo
            
        Returns:
            Solo el dominio (ej: 'gmail.com') o None
        """
        if not email or "@" not in email:
            return None
        try:
            return email.split("@")[1].lower().strip()
        except (IndexError, AttributeError):
            return None
    
    @staticmethod
    def sanitize_error_message(message: str, max_length: int = 500) -> str:
        """
        Sanitiza mensaje de error removiendo tokens y PII.
        
        Args:
            message: Mensaje de error original
            max_length: Longitud máxima
            
        Returns:
            Mensaje sanitizado
        """
        if not message:
            return ""
        
        # Truncar
        msg = message[:max_length]
        
        # No incluir tokens, emails completos, etc.
        # (el código de error ya es suficiente para debugging)
        return msg
    
    async def log_event(self, event: EmailEventData) -> Optional[str]:
        """
        Registra un nuevo evento de email usando sesión SEPARADA.
        
        Usa SessionLocal (async_sessionmaker) para crear una sesión independiente
        para que rollback en el flujo principal NO pierda los logs de email.
        Esto es crítico para métricas.
        
        Args:
            event: Datos del evento
            
        Returns:
            event_id (UUID) del evento creado, o None si falla
        """
        session_factory = self._get_event_session_factory()
        if session_factory is None:
            logger.warning("email_event_log_skipped: no session factory available")
            return None
        
        try:
            # Usar SessionLocal (async_sessionmaker) para sesión separada
            async with session_factory() as log_session:
                q = text("""
                    INSERT INTO public.auth_email_events (
                        email_type,
                        status,
                        recipient_domain,
                        user_id,
                        provider,
                        provider_message_id,
                        latency_ms,
                        error_code,
                        error_message,
                        idempotency_key,
                        correlation_id,
                        updated_at
                    ) VALUES (
                        :email_type::public.auth_email_type,
                        :status::public.auth_email_event_status,
                        :recipient_domain,
                        :user_id,
                        :provider,
                        :provider_message_id,
                        :latency_ms,
                        :error_code,
                        :error_message,
                        :idempotency_key,
                        :correlation_id,
                        CASE WHEN :status != 'pending' THEN now() ELSE NULL END
                    )
                    ON CONFLICT (idempotency_key)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        provider_message_id = COALESCE(EXCLUDED.provider_message_id, auth_email_events.provider_message_id),
                        latency_ms = COALESCE(EXCLUDED.latency_ms, auth_email_events.latency_ms),
                        error_code = COALESCE(EXCLUDED.error_code, auth_email_events.error_code),
                        error_message = COALESCE(EXCLUDED.error_message, auth_email_events.error_message),
                        updated_at = now()
                    RETURNING event_id::text
                """)
                
                result = await log_session.execute(q, {
                    "email_type": event.email_type,
                    "status": event.status,
                    "recipient_domain": event.recipient_domain,
                    "user_id": event.user_id,
                    "provider": event.provider,
                    "provider_message_id": event.provider_message_id,
                    "latency_ms": event.latency_ms,
                    "error_code": event.error_code,
                    "error_message": self.sanitize_error_message(event.error_message) if event.error_message else None,
                    "idempotency_key": event.idempotency_key,
                    "correlation_id": event.correlation_id,
                })
                
                row = result.first()
                event_id = row[0] if row else None
                
                # Commit en sesión separada - aislado del request principal
                await log_session.commit()
            
            logger.info(
                "email_event_recorded: event_id=%s email_type=%s status=%s latency_ms=%s",
                event_id,
                event.email_type,
                event.status,
                event.latency_ms,
            )
            
            return event_id
            
        except Exception as e:
            logger.error(
                "email_event_log_failed: email_type=%s status=%s error=%s",
                event.email_type,
                event.status,
                str(e),
            )
            # No fallar el envío de email por errores de logging
            return None


class EmailEventTimer:
    """
    Context manager para medir latencia de envío de email.
    
    Uso:
        timer = EmailEventTimer()
        with timer:
            await send_email(...)
        latency_ms = timer.elapsed_ms
    """
    
    def __init__(self):
        self._start: Optional[float] = None
        self._end: Optional[float] = None
    
    def __enter__(self):
        self._start = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._end = time.perf_counter()
        return False  # Don't suppress exceptions
    
    @property
    def elapsed_ms(self) -> Optional[int]:
        """Retorna latencia en milisegundos."""
        if self._start is None or self._end is None:
            return None
        return int((self._end - self._start) * 1000)


# Mapeo de métodos de email a email_type
EMAIL_METHOD_TO_TYPE: dict[str, EmailType] = {
    "send_activation_email": "account_activation",
    "send_password_reset_email": "password_reset_request",
    "send_password_reset_success_email": "password_reset_success",
    "send_welcome_email": "welcome",
    # admin notice no se trackea en métricas de auth
}


# Fin del archivo
