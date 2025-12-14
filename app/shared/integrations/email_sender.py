
# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/email_sender.py

Sender de correos con implementación 'stub' para local/test y
SMTP real para producción.

Autor: Ixchel Beristain
Actualizado: 2025-12-13
"""

import os
import logging
from typing import Protocol, Union

logger = logging.getLogger(__name__)


class IEmailSender(Protocol):
    async def send_activation_email(self, to_email: str, full_name: str, activation_token: str) -> None: ...
    async def send_password_reset_email(self, to_email: str, full_name: str, reset_token: str) -> None: ...
    async def send_welcome_email(self, to_email: str, full_name: str, credits_assigned: int) -> None: ...


class StubEmailSender:
    """Implementación que no envía correos; solo hace 'print' o logging (modo console)."""
    async def send_activation_email(self, to_email: str, full_name: str, activation_token: str) -> None:
        logger.info(f"[CONSOLE EMAIL] Activación → {to_email} | token={activation_token}")
        print(f"[STUB EMAIL] Activación → {to_email} | token={activation_token}")

    async def send_password_reset_email(self, to_email: str, full_name: str, reset_token: str) -> None:
        logger.info(f"[CONSOLE EMAIL] Reset → {to_email} | token={reset_token}")
        print(f"[STUB EMAIL] Reset → {to_email} | token={reset_token}")
    
    async def send_welcome_email(self, to_email: str, full_name: str, credits_assigned: int) -> None:
        logger.info(f"[CONSOLE EMAIL] Bienvenida → {to_email} | créditos={credits_assigned}")
        print(f"[STUB EMAIL] Bienvenida → {to_email} | {full_name} | {credits_assigned} créditos asignados")


class EmailSender:
    """Factory conmutada por variable de entorno EMAIL_MODE."""
    @staticmethod
    def from_env() -> IEmailSender:
        mode = os.getenv("EMAIL_MODE", "console").strip().lower()
        provider = os.getenv("EMAIL_PROVIDER", "").strip().lower()
        
        # Log de diagnóstico (temporal para verificar carga de .env)
        logger.warning(f"[EmailSender] mode={mode!r} provider={provider!r}")
        
        # Soportar tanto EMAIL_MODE=smtp como EMAIL_PROVIDER=smtp
        if mode == "smtp" or provider == "smtp":
            from app.shared.integrations.smtp_email_sender import SMTPEmailSender
            logger.info("Usando SMTPEmailSender para envío de correos")
            return SMTPEmailSender.from_env()
        
        if mode in ("console", "stub", "local", ""):
            logger.info("Usando StubEmailSender (modo console)")
            return StubEmailSender()
        
        logger.warning(f"EMAIL_MODE '{mode}' no reconocido, usando console")
        return StubEmailSender()


# Fin del script email_sender.py