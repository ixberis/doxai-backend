# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/email_sender.py

Factory unificado para EmailSender.
Soporta tres modos:
- console: stub que solo loguea (desarrollo/tests)
- smtp: envío via SMTP tradicional
- api: envío via API (MailerSend, etc.)

Autor: Ixchel Beristain
Actualizado: 2025-12-16
"""

from __future__ import annotations

import logging
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from app.shared.config.settings_base import BaseAppSettings

logger = logging.getLogger(__name__)


class IEmailSender(Protocol):
    """Protocolo para implementaciones de email sender."""
    async def send_activation_email(self, to_email: str, full_name: str, activation_token: str) -> None: ...
    async def send_password_reset_email(self, to_email: str, full_name: str, reset_token: str) -> None: ...
    async def send_welcome_email(self, to_email: str, full_name: str, credits_assigned: int) -> None: ...


class StubEmailSender:
    """Implementación que no envía correos; solo hace logging (modo console)."""

    async def send_activation_email(self, to_email: str, full_name: str, activation_token: str) -> None:
        logger.info(f"[CONSOLE EMAIL] Activación → {to_email} | token={activation_token[:8]}...")
        print(f"[STUB EMAIL] Activación → {to_email} | token={activation_token[:8]}...")

    async def send_password_reset_email(self, to_email: str, full_name: str, reset_token: str) -> None:
        logger.info(f"[CONSOLE EMAIL] Reset → {to_email} | token={reset_token[:8]}...")
        print(f"[STUB EMAIL] Reset → {to_email} | token={reset_token[:8]}...")

    async def send_welcome_email(self, to_email: str, full_name: str, credits_assigned: int) -> None:
        logger.info(f"[CONSOLE EMAIL] Bienvenida → {to_email} | créditos={credits_assigned}")
        print(f"[STUB EMAIL] Bienvenida → {to_email} | {full_name} | {credits_assigned} créditos asignados")


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
    def from_settings(settings: BaseAppSettings) -> IEmailSender:
        """
        Crea el email sender apropiado según settings (fuente de verdad).
        
        Args:
            settings: Configuración de la aplicación
            
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
                logger.info("[EmailSender] Usando MailerSendEmailSender")
                return MailerSendEmailSender.from_settings(settings)

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
    def from_env() -> IEmailSender:
        """
        Wrapper de compatibilidad: carga settings y delega a from_settings().
        Preferir from_settings() para mejor testabilidad.
        """
        from app.shared.config import settings
        return EmailSender.from_settings(settings)


def get_email_sender() -> IEmailSender:
    """Alias de EmailSender.from_env() para consistencia."""
    return EmailSender.from_env()


# Fin del archivo backend/app/shared/integrations/email_sender.py
