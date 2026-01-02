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
        support_email: Optional[str] = None,
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
        self.support_email = support_email or "soporte@doxai.site"

    @classmethod
    def from_settings(cls, settings) -> "SMTPEmailSender":
        """
        Crea instancia desde settings (fuente de verdad).
        
        Args:
            settings: Configuración de la aplicación (BaseAppSettings)
            
        Returns:
            SMTPEmailSender configurado
            
        Raises:
            ValueError: si faltan credenciales requeridas
        """
        server = (settings.smtp_server or "").strip()
        port = settings.smtp_port or 587
        username = (settings.smtp_username or "").strip()
        password = ""
        if settings.smtp_password:
            password = settings.smtp_password.get_secret_value().strip()
        from_email = (settings.email_from or "").strip()
        from_name = getattr(settings, "email_from_name", "DoxAI") or "DoxAI"
        use_ssl = settings.email_use_ssl
        use_tls = not use_ssl  # Si no es SSL, usa TLS
        timeout = settings.email_timeout_sec or 30
        tls_verify = getattr(settings, "email_tls_verify", True)
        support_email = getattr(settings, "support_email", None) or "soporte@doxai.site"
        # Fallback: FRONTEND_BASE_URL tiene prioridad sobre FRONTEND_URL
        frontend_url = _normalize_base_url(
            getattr(settings, "frontend_base_url", None) or settings.frontend_url
        )

        if not all([server, username, password, from_email]):
            raise ValueError(
                "EMAIL_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD y EMAIL_FROM son requeridos"
            )

        logger.info(
            "[SMTP] config: server=%s port=%s ssl=%s tls=%s tls_verify=%s reply_to=%s timeout=%ss",
            server,
            port,
            use_ssl,
            use_tls,
            tls_verify,
            support_email,
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
            support_email=support_email,
        )

    @classmethod
    def from_env(cls) -> "SMTPEmailSender":
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
        msg["Reply-To"] = self.support_email

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

    def _build_admin_activation_notice_body(
        self,
        *,
        user_email: str,
        user_name: str,
        user_id: str,
        credits_assigned: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        activation_datetime_utc: Optional[str] = None,
    ) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de notificación admin de activación."""
        from datetime import datetime, timezone

        if not activation_datetime_utc:
            activation_datetime_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        context = {
            "user_email": user_email,
            "user_name": user_name or "No especificado",
            "user_id": str(user_id),
            "activation_datetime": activation_datetime_utc,
            "credits_assigned": str(credits_assigned),
            "ip_address": ip_address or "No disponible",
            "user_agent": user_agent or "No disponible",
        }

        html, text, used_template = render_email("admin_activation_notice", context)

        if not text:
            text = (
                f"NUEVA CUENTA ACTIVADA - DoxAI\n"
                f"==============================\n\n"
                f"Email: {user_email}\n"
                f"Nombre: {user_name or 'No especificado'}\n"
                f"User ID: {user_id}\n"
                f"Fecha/Hora: {activation_datetime_utc} UTC\n"
                f"Créditos: {credits_assigned}\n"
                f"IP: {ip_address or 'No disponible'}\n"
            )

        if not html:
            html = f"<pre>{text}</pre>"

        return html, text, used_template

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
        """
        Envía notificación al admin cuando un usuario activa su cuenta.
        
        Args:
            to_email: Email del admin (normalmente doxai@doxai.site)
            user_email: Email del usuario que activó
            user_name: Nombre del usuario
            user_id: ID del usuario
            credits_assigned: Créditos asignados
            ip_address: IP del usuario (opcional)
            user_agent: User agent del navegador (opcional)
            activation_datetime_utc: Fecha/hora de activación (opcional, default=now)
        """
        html, text, used_template = self._build_admin_activation_notice_body(
            user_email=user_email,
            user_name=user_name,
            user_id=user_id,
            credits_assigned=credits_assigned,
            ip_address=ip_address,
            user_agent=user_agent,
            activation_datetime_utc=activation_datetime_utc,
        )

        logger.info(
            "[SMTP] admin activation notice: to=%s user=%s user_id=%s template=%s",
            to_email,
            user_email[:3] + "***" if user_email else "unknown",
            user_id,
            "loaded" if used_template else "fallback",
        )

        await asyncio.to_thread(
            self._send_sync,
            to_email,
            f"Cuenta activada en DoxAI - {user_email}",
            html,
            text,
        )

    def _build_password_reset_success_body(
        self,
        *,
        full_name: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reset_datetime_utc: Optional[str] = None,
    ) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de notificación de reset exitoso."""
        from datetime import datetime, timezone

        if not reset_datetime_utc:
            reset_datetime_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        login_url = f"{self.frontend_url}/auth/login" if self.frontend_url else ""

        context = {
            "user_name": full_name or "Usuario",
            "reset_datetime": reset_datetime_utc,
            "ip_address": ip_address or "No disponible",
            "user_agent": user_agent or "No disponible",
            "login_url": login_url,
            "frontend_url": self.frontend_url or "",
            "support_email": self.support_email,
        }

        html, text, used_template = render_email("password_reset_success_email", context)

        if not text:
            text = (
                f"CONTRASEÑA RESTABLECIDA - DoxAI\n"
                f"================================\n\n"
                f"Hola {full_name or 'Usuario'},\n\n"
                f"Su contraseña ha sido restablecida exitosamente.\n\n"
                f"Fecha/Hora: {reset_datetime_utc} UTC\n"
                f"IP: {ip_address or 'No disponible'}\n\n"
                f"Si usted no realizó este cambio, contacte soporte: {self.support_email}\n"
            )

        if not html:
            html = f"<pre>{text}</pre>"

        return html, text, used_template

    async def send_password_reset_success_email(
        self,
        to_email: str,
        *,
        full_name: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reset_datetime_utc: Optional[str] = None,
    ) -> None:
        """
        Envía notificación al usuario cuando su contraseña fue restablecida.
        
        Args:
            to_email: Email del usuario
            full_name: Nombre del usuario
            ip_address: IP desde donde se hizo el reset (opcional)
            user_agent: User agent del navegador (opcional)
            reset_datetime_utc: Fecha/hora del reset (opcional, default=now)
        """
        html, text, used_template = self._build_password_reset_success_body(
            full_name=full_name,
            ip_address=ip_address,
            user_agent=user_agent,
            reset_datetime_utc=reset_datetime_utc,
        )

        logger.info(
            "[SMTP] password_reset_success: to=%s template=%s",
            to_email[:3] + "***" if to_email else "unknown",
            "loaded" if used_template else "fallback",
        )

        await asyncio.to_thread(
            self._send_sync,
            to_email,
            "Su contraseña fue restablecida - DoxAI",
            html,
            text,
        )


# Fin del archivo backend/app/shared/integrations/smtp_email_sender.py
