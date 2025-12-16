# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/mailersend_email_sender.py

Implementación de envío de correos usando MailerSend API.
Usa templates de templates/emails/ como fuente de verdad.

Autor: Ixchel Beristain
Creado: 2025-12-16

Notas:
- MailerSend API es más confiable que SMTP en entornos cloud (Railway, Vercel).
- No requiere TLS cert validation del sistema operativo.
- Soporta tracking de emails y webhooks (no implementados aquí).
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple, TYPE_CHECKING

import httpx

from app.shared.integrations.email_templates import (
    render_email,
    mask_token,
    get_fallback_text,
)

if TYPE_CHECKING:
    from app.shared.config.settings_base import BaseAppSettings

logger = logging.getLogger(__name__)

# MailerSend API endpoint
MAILERSEND_API_URL = "https://api.mailersend.com/v1/email"


def _normalize_base_url(url: Optional[str]) -> Optional[str]:
    """Normaliza una URL base (quita espacios y slash final)."""
    if not url:
        return None
    u = url.strip()
    return u.rstrip("/") if u else None


class MailerSendEmailSender:
    """Envío de correos usando MailerSend API."""

    def __init__(
        self,
        api_key: str,
        from_email: str,
        from_name: str = "DoxAI",
        timeout: int = 30,
        frontend_url: Optional[str] = None,
    ):
        if not api_key:
            raise ValueError("MAILERSEND_API_KEY es requerido")
        if not from_email:
            raise ValueError("MAILERSEND_FROM_EMAIL es requerido")

        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name
        self.timeout = timeout
        self.frontend_url = _normalize_base_url(frontend_url)

    @classmethod
    def from_settings(cls, settings: BaseAppSettings) -> "MailerSendEmailSender":
        """
        Crea instancia desde settings (fuente de verdad).
        
        Args:
            settings: Configuración de la aplicación
            
        Returns:
            MailerSendEmailSender configurado
            
        Raises:
            ValueError: si faltan credenciales requeridas
        """
        # Extraer valores de settings
        api_key = ""
        if settings.mailersend_api_key:
            api_key = settings.mailersend_api_key.get_secret_value().strip()
        
        from_email = (settings.mailersend_from_email or "").strip()
        from_name = (settings.mailersend_from_name or "DoxAI").strip()
        timeout = settings.email_timeout_sec or 30
        # Fallback: FRONTEND_BASE_URL tiene prioridad sobre FRONTEND_URL
        frontend_url = _normalize_base_url(
            getattr(settings, "frontend_base_url", None) or settings.frontend_url
        )

        if not api_key:
            raise ValueError(
                "[MailerSend] MAILERSEND_API_KEY es requerido. "
                "Configúrelo en Railway/Vercel."
            )
        if not from_email:
            raise ValueError(
                "[MailerSend] MAILERSEND_FROM_EMAIL es requerido. "
                "Configúrelo en Railway/Vercel."
            )

        logger.info(
            "[MailerSend] config: from=%s (%s) timeout=%ss",
            from_email,
            from_name,
            timeout,
        )

        return cls(
            api_key=api_key,
            from_email=from_email,
            from_name=from_name,
            timeout=timeout,
            frontend_url=frontend_url,
        )

    @classmethod
    def from_env(cls) -> "MailerSendEmailSender":
        """
        Wrapper de compatibilidad: carga settings y delega a from_settings().
        Preferir from_settings() para mejor testabilidad.
        """
        from app.shared.config import settings
        return cls.from_settings(settings)

    def _build_activation_body(
        self, full_name: str, activation_token: str
    ) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de activación."""
        user_name = full_name or "Usuario"
        activation_link = ""
        if self.frontend_url:
            activation_link = f"{self.frontend_url}/auth/activate?token={activation_token}"

        context = {
            "user_name": user_name,
            "activation_link": activation_link,
            "frontend_url": self.frontend_url or "",
            "expiration_hours": "1",
        }

        html, text, used_template = render_email("activation_email", context)

        if not text:
            text = get_fallback_text(
                "activation" if activation_link else "activation_no_link",
                context,
            )

        if not html:
            html = f"<pre>{text}</pre>"

        return html, text, used_template

    def _build_password_reset_body(
        self, full_name: str, reset_token: str
    ) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de reset de contraseña."""
        user_name = full_name or "Usuario"
        reset_link = ""
        if self.frontend_url:
            reset_link = f"{self.frontend_url}/auth/reset-password?token={reset_token}"

        context = {
            "user_name": user_name,
            "reset_link": reset_link,
            "reset_url": reset_link,
            "frontend_url": self.frontend_url or "",
            "expiration_hours": "1",
        }

        html, text, used_template = render_email("password_reset_email", context)

        if not text:
            text = get_fallback_text("password_reset", context)

        if not html:
            html = f"<pre>{text}</pre>"

        return html, text, used_template

    def _build_welcome_body(
        self, full_name: str, credits_assigned: int
    ) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de bienvenida."""
        user_name = full_name or "Usuario"

        context = {
            "user_name": user_name,
            "credits_assigned": str(credits_assigned),
            "frontend_url": self.frontend_url or "",
        }

        html, text, used_template = render_email("welcome_email", context)

        if not text:
            text = get_fallback_text("welcome", context)

        if not html:
            html = f"<pre>{text}</pre>"

        return html, text, used_template

    async def _send_email(
        self, to_email: str, subject: str, html_body: str, text_body: str
    ) -> str:
        """Envía email via MailerSend API. Retorna message_id."""
        payload = {
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "to": [
                {"email": to_email}
            ],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "[MailerSend] sending: to=%s subject=%s from=%s",
            to_email,
            subject,
            self.from_email,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    MAILERSEND_API_URL,
                    json=payload,
                    headers=headers,
                )

                # MailerSend returns 202 Accepted on success
                if response.status_code == 202:
                    message_id = response.headers.get("X-Message-Id", "accepted")
                    logger.info(
                        "[MailerSend] sent ok: to=%s message_id=%s",
                        to_email,
                        message_id,
                    )
                    return message_id

                # Handle errors - try to parse JSON if available
                error_body = response.text
                content_type = response.headers.get("Content-Type", "")
                
                if "application/json" in content_type:
                    try:
                        error_json = response.json()
                        logger.error(
                            "[MailerSend] send failed: to=%s status=%d json=%s",
                            to_email,
                            response.status_code,
                            error_json,
                        )
                    except Exception:
                        logger.error(
                            "[MailerSend] send failed: to=%s status=%d body=%s",
                            to_email,
                            response.status_code,
                            error_body[:500],
                        )
                else:
                    logger.error(
                        "[MailerSend] send failed: to=%s status=%d body=%s",
                        to_email,
                        response.status_code,
                        error_body[:500],
                    )

                raise RuntimeError(
                    f"MailerSend API error: {response.status_code} - {error_body[:200]}"
                )

            except httpx.TimeoutException as e:
                logger.error("[MailerSend] timeout: to=%s error=%s", to_email, str(e))
                raise RuntimeError(f"MailerSend timeout: {e}") from e
            except httpx.RequestError as e:
                logger.error("[MailerSend] request error: to=%s error=%s", to_email, str(e))
                raise RuntimeError(f"MailerSend request error: {e}") from e

    async def send_activation_email(
        self, to_email: str, full_name: str, activation_token: str
    ) -> None:
        """Envía email de activación de cuenta."""
        html, text, used_template = self._build_activation_body(
            full_name, activation_token
        )

        logger.info(
            "[MailerSend] activation email: to=%s user=%s token=%s template=%s",
            to_email,
            full_name or "Usuario",
            mask_token(activation_token),
            "loaded" if used_template else "fallback",
        )

        await self._send_email(to_email, "Active su cuenta en DoxAI", html, text)

    async def send_password_reset_email(
        self, to_email: str, full_name: str, reset_token: str
    ) -> None:
        """Envía email de reset de contraseña."""
        html, text, used_template = self._build_password_reset_body(
            full_name, reset_token
        )

        logger.info(
            "[MailerSend] password reset: to=%s user=%s token=%s template=%s",
            to_email,
            full_name or "Usuario",
            mask_token(reset_token),
            "loaded" if used_template else "fallback",
        )

        await self._send_email(to_email, "Restablecer contraseña - DoxAI", html, text)

    async def send_welcome_email(
        self, to_email: str, full_name: str, credits_assigned: int
    ) -> None:
        """Envía email de bienvenida."""
        html, text, used_template = self._build_welcome_body(full_name, credits_assigned)

        logger.info(
            "[MailerSend] welcome email: to=%s user=%s credits=%d template=%s",
            to_email,
            full_name or "Usuario",
            credits_assigned,
            "loaded" if used_template else "fallback",
        )

        await self._send_email(to_email, "Bienvenido a DoxAI", html, text)


# Fin del archivo backend/app/shared/integrations/mailersend_email_sender.py
