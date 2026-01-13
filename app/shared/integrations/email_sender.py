# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/email_sender.py

Factory unificado para EmailSender.
Soporta tres modos:
- console: stub que solo loguea (desarrollo/tests)
- smtp: envío via SMTP tradicional
- api: envío via API (MailerSend, etc.)

Autor: Ixchel Beristain
Actualizado: 2026-01-03 - Soporte para db_session (instrumentación de eventos)
"""

from __future__ import annotations

import logging
from typing import Protocol, Optional, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.shared.config.settings_base import BaseAppSettings
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class IEmailSender(Protocol):
    """Protocolo para implementaciones de email sender.
    
    DB 2.0 SSOT: Todos los métodos aceptan auth_user_id (UUID) opcional
    para garantizar que los eventos de email se persistan correctamente.
    """
    async def send_activation_email(
        self, 
        to_email: str, 
        full_name: str, 
        activation_token: str,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> None: ...
    
    async def send_password_reset_email(
        self, 
        to_email: str, 
        full_name: str, 
        reset_token: str,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> None: ...
    
    async def send_welcome_email(
        self, 
        to_email: str, 
        full_name: str, 
        credits_assigned: int,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> None: ...
    
    async def send_admin_activation_notice(
        self,
        to_email: str,
        *,
        user_email: str,
        user_name: str,
        user_id: str,
        credits_assigned: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        activation_datetime_utc: Optional[str] = None,
    ) -> None: ...
    
    async def send_password_reset_success_email(
        self,
        to_email: str,
        *,
        full_name: str,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reset_datetime_utc: Optional[str] = None,
    ) -> None: ...
    
    async def send_purchase_confirmation_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """Envía email de confirmación de compra. Retorna provider_message_id."""
        ...


class StubEmailSender:
    """Implementación que no envía correos; solo hace logging (modo console).
    
    Acepta auth_user_id y correlation_id para compatibilidad con IEmailSender,
    pero no los persiste (solo logging en consola).
    """

    async def send_activation_email(
        self, 
        to_email: str, 
        full_name: str, 
        activation_token: str,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        logger.info(f"[CONSOLE EMAIL] Activación → {to_email} | token={activation_token[:8]}... auth_user_id={auth_user_id}")
        print(f"[STUB EMAIL] Activación → {to_email} | token={activation_token[:8]}...")

    async def send_password_reset_email(
        self, 
        to_email: str, 
        full_name: str, 
        reset_token: str,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        logger.info(f"[CONSOLE EMAIL] Reset → {to_email} | token={reset_token[:8]}... auth_user_id={auth_user_id}")
        print(f"[STUB EMAIL] Reset → {to_email} | token={reset_token[:8]}...")

    async def send_welcome_email(
        self, 
        to_email: str, 
        full_name: str, 
        credits_assigned: int,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        logger.info(f"[CONSOLE EMAIL] Bienvenida → {to_email} | créditos={credits_assigned} auth_user_id={auth_user_id}")
        print(f"[STUB EMAIL] Bienvenida → {to_email} | {full_name} | {credits_assigned} créditos asignados")

    async def send_admin_activation_notice(
        self,
        to_email: str,
        *,
        user_email: str,
        user_name: str,
        user_id: str,
        credits_assigned: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        activation_datetime_utc: Optional[str] = None,
    ) -> None:
        logger.info(
            f"[CONSOLE EMAIL] Admin notice → {to_email} | user={user_email} id={user_id} credits={credits_assigned}"
        )
        print(
            f"[STUB EMAIL] Admin activation notice → {to_email}\n"
            f"  User: {user_email} ({user_name})\n"
            f"  ID: {user_id}\n"
            f"  Credits: {credits_assigned}\n"
            f"  IP: {ip_address or 'N/A'}\n"
            f"  DateTime: {activation_datetime_utc or 'N/A'}"
        )

    async def send_password_reset_success_email(
        self,
        to_email: str,
        *,
        full_name: str,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reset_datetime_utc: Optional[str] = None,
    ) -> None:
        logger.info(
            f"[CONSOLE EMAIL] Password reset success → {to_email} | user={full_name} auth_user_id={auth_user_id}"
        )
        print(
            f"[STUB EMAIL] Password reset success → {to_email}\n"
            f"  User: {full_name}\n"
            f"  IP: {ip_address or 'N/A'}\n"
            f"  DateTime: {reset_datetime_utc or 'N/A'}"
        )

    async def send_purchase_confirmation_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> str:
        """Stub para email de confirmación de compra. Retorna message_id ficticio."""
        from uuid import uuid4
        message_id = f"stub-{uuid4().hex[:16]}"
        logger.info(
            f"[CONSOLE EMAIL] Purchase confirmation → {to_email} | subject={subject[:30]}... auth_user_id={auth_user_id}"
        )
        print(
            f"[STUB EMAIL] Purchase confirmation → {to_email}\n"
            f"  Subject: {subject}\n"
            f"  Message ID: {message_id}"
        )
        return message_id


class EmailSender:
    """
    Factory unificado para selección de email sender.
    
    Variables de entorno (via settings):
    - email_mode: console | smtp | api
    - email_provider: smtp | mailersend (usado cuando email_mode=api)
    
    Ejemplos de configuración:
    - Desarrollo: EMAIL_MODE=console
    - SMTP: EMAIL_MODE=smtp + EMAIL_SERVER, EMAIL_USERNAME, etc.
    - MailerSend: EMAIL_MODE=api + EMAIL_PROVIDER=mailersend + MAILERSEND_API_KEY, etc.
    """

    @staticmethod
    def from_settings(
        settings: "BaseAppSettings",
        db_session: Optional["AsyncSession"] = None,
    ) -> IEmailSender:
        """
        Crea el email sender apropiado según settings (fuente de verdad).
        
        Args:
            settings: Configuración de la aplicación
            db_session: Sesión de base de datos (legacy, para compatibilidad)
            
        Returns:
            IEmailSender: implementación según configuración
            
        Raises:
            ValueError: si email_mode=api pero faltan credenciales
        """
        mode = (settings.email_mode or "console").strip().lower()
        provider = (settings.email_provider or "").strip().lower()

        logger.info(f"[EmailSender] mode={mode!r} provider={provider!r}")

        # ─────────────────────────────────────────────────────────────
        # PROVIDER OVERRIDE - provider="smtp" tiene prioridad sobre mode
        # ─────────────────────────────────────────────────────────────
        if provider == "smtp":
            from app.shared.integrations.smtp_email_sender import SMTPEmailSender
            logger.info("[EmailSender] Usando SMTPEmailSender (provider override)")
            return SMTPEmailSender.from_settings(settings)

        # ─────────────────────────────────────────────────────────────
        # MODO CONSOLE (stub) - desarrollo y tests
        # ─────────────────────────────────────────────────────────────
        if mode in ("console", "stub", "local", ""):
            logger.info("[EmailSender] Usando StubEmailSender (modo console)")
            return StubEmailSender()

        # ─────────────────────────────────────────────────────────────
        # MODO SMTP - envío tradicional
        # ─────────────────────────────────────────────────────────────
        if mode == "smtp":
            from app.shared.integrations.smtp_email_sender import SMTPEmailSender
            logger.info("[EmailSender] Usando SMTPEmailSender")
            return SMTPEmailSender.from_settings(settings)

        # ─────────────────────────────────────────────────────────────
        # MODO API - proveedores externos (MailerSend, etc.)
        # ─────────────────────────────────────────────────────────────
        if mode == "api":
            # MailerSend es el proveedor por defecto para modo API
            if provider in ("mailersend", ""):
                from app.shared.integrations.mailersend_email_sender import MailerSendEmailSender
                
                # CRÍTICO: Pasar SessionLocal explícitamente para instrumentación de eventos
                # Guard estructural: verificar que factory() retorna async context manager
                event_session_factory = None
                disable_reason = None
                
                try:
                    from app.shared.database.database import SessionLocal
                    
                    if SessionLocal is None:
                        disable_reason = "SessionLocal=None (SKIP_DB_INIT?)"
                    elif not callable(SessionLocal):
                        disable_reason = f"SessionLocal not callable ({type(SessionLocal).__name__})"
                    else:
                        # Guard estructural: verificar que factory() retorna async context manager
                        try:
                            test_cm = SessionLocal()
                            if not hasattr(test_cm, "__aenter__") or not hasattr(test_cm, "__aexit__"):
                                disable_reason = "factory() lacks __aenter__/__aexit__"
                            else:
                                # Válido: es async context manager
                                event_session_factory = SessionLocal
                        except Exception as factory_err:
                            disable_reason = f"factory() raised: {factory_err}"
                            
                except ImportError as e:
                    disable_reason = f"ImportError: {e}"
                
                # Log único explícito de modo de logging (clave para operación)
                if event_session_factory:
                    logger.info(
                        "email_event_logging_mode=factory SessionLocal_type=%s",
                        type(event_session_factory).__name__,
                    )
                else:
                    logger.warning(
                        "email_event_logging_mode=disabled reason=%s",
                        disable_reason,
                    )
                
                return MailerSendEmailSender.from_settings(
                    settings, 
                    db_session=db_session, 
                    event_session_factory=event_session_factory
                )

            # Proveedor no reconocido en modo API
            logger.error(
                f"[EmailSender] EMAIL_PROVIDER={provider!r} no reconocido para EMAIL_MODE=api. "
                f"Proveedores soportados: mailersend"
            )
            raise ValueError(
                f"EMAIL_PROVIDER '{provider}' no soportado. "
                f"Configure EMAIL_PROVIDER=mailersend o cambie EMAIL_MODE."
            )

        # ─────────────────────────────────────────────────────────────
        # MODO NO RECONOCIDO - fail-fast en producción
        # ─────────────────────────────────────────────────────────────
        if settings.is_prod:
            logger.error(
                f"[EmailSender] EMAIL_MODE={mode!r} no reconocido en producción. "
                f"Valores válidos: console, smtp, api"
            )
            raise ValueError(
                f"EMAIL_MODE '{mode}' no reconocido. "
                f"Configure EMAIL_MODE=console|smtp|api"
            )

        # En desarrollo, fallback a console con warning
        logger.warning(
            f"[EmailSender] EMAIL_MODE={mode!r} no reconocido, usando console (solo dev)"
        )
        return StubEmailSender()

    @staticmethod
    def from_env(db_session: Optional["AsyncSession"] = None) -> IEmailSender:
        """
        Wrapper de compatibilidad: carga settings y delega a from_settings().
        Preferir from_settings() para mejor testabilidad.
        
        Args:
            db_session: Sesión de base de datos para instrumentación de eventos
        """
        from app.shared.config import settings
        return EmailSender.from_settings(settings, db_session=db_session)


def get_email_sender(db_session: Optional["AsyncSession"] = None) -> IEmailSender:
    """Alias de EmailSender.from_env() para consistencia."""
    return EmailSender.from_env(db_session=db_session)


# Fin del archivo backend/app/shared/integrations/email_sender.py
