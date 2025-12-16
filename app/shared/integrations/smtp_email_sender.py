# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/smtp_email_sender.py

Implementación de envío de correos por SMTP.
Usa templates de templates/emails/ como fuente de verdad.

Autor: Ixchel Beristain
Actualizado: 2025-12-16

Notas:
- En entornos tipo Railway/Nixpacks, a veces el runtime no tiene un CA bundle
  confiable para OpenSSL/Python, y se observa:
    [SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain
  incluso cuando el servidor usa Let's Encrypt.
- Para evitar dependencia del CA bundle del sistema, cuando EMAIL_TLS_VERIFY=true
  usamos certifi.where() como cafile (Mozilla CA bundle).
- Para desbloquear staging sin romper prod, se mantiene el flag:
    EMAIL_TLS_VERIFY=true|false (default: true)
  Si EMAIL_TLS_VERIFY=false, se usa un contexto TLS sin verificación.
"""

import os
import ssl
import smtplib
import logging
import asyncio
from email.message import EmailMessage
from email.utils import formatdate, formataddr, make_msgid
from typing import Optional, Tuple

import certifi  # ✅ CA bundle confiable (Mozilla), evita issues en runtimes minimalistas

from app.shared.integrations.email_templates import (
    render_email,
    mask_token,
    get_fallback_text,
)

logger = logging.getLogger(__name__)


def _normalize_base_url(url: Optional[str]) -> Optional[str]:
    """Normaliza una URL base (quita espacios y slash final)."""
    if not url:
        return None
    u = url.strip()
    return u.rstrip("/") if u else None


def _env_bool(name: str, default: bool = False) -> bool:
    """Lee booleanos desde env con valores típicos."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def _build_tls_context(verify: bool) -> ssl.SSLContext:
    """
    Construye un SSLContext para SMTP.

    verify=True  -> contexto con verificación (usa CA bundle de certifi)
    verify=False -> contexto SIN verificación (útil cuando el SMTP presenta cadena inválida)
    """
    if verify:
        # ✅ Usar CA bundle de certifi (Mozilla), independiente del sistema operativo
        # Evita fallas típicas en Railway/Nixpacks por ausencia de ca-certificates.
        ctx = ssl.create_default_context(cafile=certifi.where())
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    # ⚠️ Deshabilita validación de certificados/hostname.
    # Se mantiene cifrado, pero sin verificación de identidad del servidor.
    ctx = ssl._create_unverified_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class SMTPEmailSender:
    """Envío de correos por SMTP con soporte SSL/TLS y templates."""

    def __init__(
        self,
        server: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str = "DoxAI",
        use_ssl: bool = True,
        use_tls: bool = False,
        timeout: int = 30,
        templates_dir: Optional[str] = None,  # Deprecated, ignorado
        frontend_url: Optional[str] = None,
        tls_verify: bool = True,
    ):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.from_name = from_name
        self.use_ssl = use_ssl
        self.use_tls = use_tls
        self.timeout = timeout
        self.frontend_url = _normalize_base_url(frontend_url)
        self.tls_verify = tls_verify

    @classmethod
    def from_env(cls) -> "SMTPEmailSender":
        """Crea instancia desde variables de entorno."""
        server = os.getenv("EMAIL_SERVER", "").strip()
        port = int(os.getenv("EMAIL_PORT", "587").strip())
        username = os.getenv("EMAIL_USERNAME", "").strip()
        password = os.getenv("EMAIL_PASSWORD", "").strip()
        from_email = os.getenv("EMAIL_FROM", "").strip()
        from_name = os.getenv("EMAIL_FROM_NAME", "DoxAI").strip()
        use_ssl = os.getenv("EMAIL_USE_SSL", "false").lower().strip() == "true"
        use_tls = os.getenv("EMAIL_USE_TLS", "true").lower().strip() == "true"
        timeout = int(os.getenv("EMAIL_TIMEOUT_SEC", "30").strip())

        # control de verificación TLS
        tls_verify = _env_bool("EMAIL_TLS_VERIFY", default=True)

        frontend_url = _normalize_base_url(
            os.getenv("FRONTEND_BASE_URL", "").strip()
            or os.getenv("FRONTEND_URL", "").strip()
        )

        if not all([server, username, password, from_email]):
            raise ValueError(
                "EMAIL_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD y EMAIL_FROM son requeridos"
            )

        logger.info(
            "[SMTP] config: server=%s port=%s ssl=%s tls=%s tls_verify=%s timeout=%ss",
            server,
            port,
            use_ssl,
            use_tls,
            tls_verify,
            timeout,
        )

        return cls(
            server=server,
            port=port,
            username=username,
            password=password,
            from_email=from_email,
            from_name=from_name,
            use_ssl=use_ssl,
            use_tls=use_tls,
            timeout=timeout,
            frontend_url=frontend_url,
            tls_verify=tls_verify,
        )

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
            "reset_url": reset_link,  # Alias para compatibilidad
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

    def build_email_message(
        self, to_email: str, subject: str, html_body: str, text_body: str
    ) -> EmailMessage:
        """Construye EmailMessage con headers robustos."""
        msg = EmailMessage()
        msg["From"] = formataddr((self.from_name, self.from_email))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)

        domain = (
            self.from_email.split("@")[-1] if "@" in self.from_email else "doxai.local"
        )
        msg["Message-ID"] = make_msgid(domain=domain)

        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        return msg

    def _send_sync(
        self, to_email: str, subject: str, html_body: str, text_body: str
    ) -> str:
        """Envío síncrono por SMTP. Retorna Message-ID."""
        msg = self.build_email_message(to_email, subject, html_body, text_body)

        logger.info(
            "[SMTP] sending: to=%s subject=%s via=%s:%s ssl=%s tls=%s tls_verify=%s",
            to_email,
            subject,
            self.server,
            self.port,
            self.use_ssl,
            self.use_tls,
            self.tls_verify,
        )

        smtp_debug = os.getenv("EMAIL_SMTP_DEBUG", "false").lower() == "true"
        context = _build_tls_context(self.tls_verify)

        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(
                    self.server, self.port, context=context, timeout=self.timeout
                ) as server:
                    if smtp_debug:
                        server.set_debuglevel(1)
                    server.login(self.username, self.password)
                    refused = server.send_message(msg)
                    msg_id = msg.get("Message-ID", "unknown")
                    if refused:
                        logger.warning("[SMTP] refused: %s", refused)
                    logger.info("[SMTP] sent ok to=%s msg_id=%s", to_email, msg_id)
                    return msg_id
            else:
                with smtplib.SMTP(
                    self.server, self.port, timeout=self.timeout
                ) as server:
                    if smtp_debug:
                        server.set_debuglevel(1)
                    server.ehlo()
                    if self.use_tls:
                        if self.tls_verify:
                            # STARTTLS con verificación normal usando CA bundle de certifi
                            server.starttls(context=context)
                        else:
                            # STARTTLS SIN verificación (self-signed / cadena incompleta)
                            server.starttls(context=context)
                        server.ehlo()
                    server.login(self.username, self.password)
                    refused = server.send_message(msg)
                    msg_id = msg.get("Message-ID", "unknown")
                    if refused:
                        logger.warning("[SMTP] refused: %s", refused)
                    logger.info("[SMTP] sent ok to=%s msg_id=%s", to_email, msg_id)
                    return msg_id

        except Exception:
            logger.exception("[SMTP] send failed to=%s", to_email)
            raise

    async def send_activation_email(
        self, to_email: str, full_name: str, activation_token: str
    ) -> None:
        """Envía email de activación de cuenta."""
        html, text, used_template = self._build_activation_body(
            full_name, activation_token
        )

        logger.info(
            "[SMTP] activation email: to=%s user=%s token=%s template=%s",
            to_email,
            full_name or "Usuario",
            mask_token(activation_token),
            "loaded" if used_template else "fallback",
        )

        await asyncio.to_thread(
            self._send_sync, to_email, "Active su cuenta en DoxAI", html, text
        )

    async def send_password_reset_email(
        self, to_email: str, full_name: str, reset_token: str
    ) -> None:
        """Envía email de reset de contraseña."""
        html, text, used_template = self._build_password_reset_body(
            full_name, reset_token
        )

        logger.info(
            "[SMTP] password reset: to=%s user=%s token=%s template=%s",
            to_email,
            full_name or "Usuario",
            mask_token(reset_token),
            "loaded" if used_template else "fallback",
        )

        await asyncio.to_thread(
            self._send_sync, to_email, "Restablecer contraseña - DoxAI", html, text
        )

    async def send_welcome_email(
        self, to_email: str, full_name: str, credits_assigned: int
    ) -> None:
        """Envía email de bienvenida."""
        html, text, used_template = self._build_welcome_body(full_name, credits_assigned)

        logger.info(
            "[SMTP] welcome email: to=%s user=%s credits=%d template=%s",
            to_email,
            full_name or "Usuario",
            credits_assigned,
            "loaded" if used_template else "fallback",
        )

        await asyncio.to_thread(
            self._send_sync, to_email, "Bienvenido a DoxAI", html, text
        )

# Fin del archivo backend/app/shared/integrations/smtp_email_sender.py
