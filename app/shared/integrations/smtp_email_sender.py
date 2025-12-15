# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/smtp_email_sender.py

Implementación real de envío de correos por SMTP.
Soporta SSL directo o STARTTLS, templates HTML y fallbacks.
Multipart/alternative con headers robustos para entregabilidad.

Ajustes:
- FRONTEND_BASE_URL como fuente de verdad (compat: FRONTEND_URL)
- Normalización de URL (sin slash final)
- Resolución robusta de EMAIL_TEMPLATES_DIR (absoluto o relativo al repo/backend)

Autor: Ixchel Beristain
Actualizado: 2025-12-15
"""

import os
import ssl
import smtplib
import logging
import asyncio
from email.message import EmailMessage
from email.utils import formatdate, formataddr, make_msgid
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _normalize_base_url(url: Optional[str]) -> Optional[str]:
    """Normaliza una URL base (quita espacios y slash final)."""
    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    return u.rstrip("/")


def _resolve_templates_dir(raw: str) -> Optional[Path]:
    """
    Resuelve EMAIL_TEMPLATES_DIR:
    - Si es absoluto y existe -> se usa
    - Si es relativo -> intenta relativo al CWD, al backend/, y al archivo actual (shared/)
    """
    if not raw:
        return None

    p = Path(raw.strip())
    candidates = []

    # 1) Tal cual (absoluto o relativo al CWD)
    candidates.append(p)

    # 2) Relativo al backend/ (si estamos ejecutando desde repo root)
    candidates.append(Path.cwd() / p)

    # 3) Relativo al repo (dos niveles arriba de backend/app/shared/integrations/)
    # smtp_email_sender.py -> integrations -> shared -> app -> backend
    backend_root = Path(__file__).resolve().parents[3]
    candidates.append(backend_root / p)

    # 4) Si alguien pone "app/shared/templates" relativo a backend
    candidates.append(backend_root / "app" / "shared" / "templates")

    for c in candidates:
        try:
            if c.exists():
                return c.resolve()
        except Exception:
            continue

    return None


class SMTPEmailSender:
    """Envío real de correos por SMTP con soporte SSL/TLS."""

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
        templates_dir: Optional[str] = None,
        frontend_url: Optional[str] = None,
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

        # templates_dir: si viene, se resuelve; si no, usamos default backend/app/shared/templates
        resolved_templates: Optional[Path] = None
        if templates_dir:
            resolved_templates = _resolve_templates_dir(templates_dir)

        if resolved_templates and resolved_templates.exists():
            self.templates_dir = resolved_templates
            logger.info("[SMTP] templates_dir resolved: %s", resolved_templates)
        else:
            default_path = Path(__file__).resolve().parents[1] / "templates"  # shared/templates
            if default_path.exists():
                self.templates_dir = default_path
                logger.info("[SMTP] Using default templates_dir: %s", default_path)
            else:
                self.templates_dir = None
                logger.warning("[SMTP] No templates_dir set and default not found: %s", default_path)

        # frontend_url: normalizada
        self.frontend_url = _normalize_base_url(frontend_url)

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

        templates_dir_env = os.getenv("EMAIL_TEMPLATES_DIR", "").strip()

        # ✅ Fuente de verdad: FRONTEND_BASE_URL (compat: FRONTEND_URL)
        frontend_url = (
            os.getenv("FRONTEND_BASE_URL", "").strip()
            or os.getenv("FRONTEND_URL", "").strip()
        )
        frontend_url = _normalize_base_url(frontend_url)

        if not all([server, username, password, from_email]):
            raise ValueError("EMAIL_SERVER, EMAIL_USERNAME, EMAIL_PASSWORD y EMAIL_FROM son requeridos")

        # Resolver templates_dir si viene en env
        templates_dir_path: Optional[Path] = None
        if templates_dir_env:
            templates_dir_path = _resolve_templates_dir(templates_dir_env)
            logger.warning(
                "[SMTP] templates_dir from env: %s (exists=%s)",
                templates_dir_env,
                bool(templates_dir_path and templates_dir_path.exists()),
            )
        else:
            logger.info("[SMTP] templates_dir not set in env, will use default")

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
            templates_dir=str(templates_dir_path) if templates_dir_path else None,
            frontend_url=frontend_url,
        )

    def _load_template(self, template_name: str) -> Optional[str]:
        """Carga template HTML desde disco si existe."""
        if not self.templates_dir:
            return None
        template_path = self.templates_dir / template_name
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return None

    def _mask_token(self, token: str) -> str:
        """Enmascara token para logging seguro."""
        if len(token) <= 8:
            return "****"
        return f"{token[:4]}...{token[-4:]}"

    def _build_activation_body(self, full_name: str, activation_token: str) -> Tuple[str, str, bool]:
        """
        Construye cuerpo para email de activación.

        Retorna: (html, text, used_template)
        - HTML: NO incluye URL visible (solo en href del botón)
        - text/plain: SÍ incluye URL completa para accesibilidad
        """
        template = self._load_template("activation_email.html")
        used_template = template is not None

        activation_link = ""
        if self.frontend_url:
            activation_link = f"{self.frontend_url}/auth/activate?token={activation_token}"

        user_name = full_name or "Usuario"
        frontend_url = self.frontend_url or ""

        if template:
            html = template.replace("{{ user_name }}", user_name).replace("{{user_name}}", user_name)
            html = html.replace("{{ activation_link }}", activation_link).replace("{{activation_link}}", activation_link)
            html = html.replace("{{ frontend_url }}", frontend_url).replace("{{frontend_url}}", frontend_url)
        else:
            if activation_link:
                html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
  <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden;">
    <div style="background: linear-gradient(135deg, #4A6CF7 0%, #3651D4 100%); color: white; text-align: center; padding: 30px 20px;">
      <h1 style="margin: 0; font-size: 24px;">Bienvenido a DoxAI</h1>
    </div>
    <div style="padding: 30px 20px;">
      <p style="color: #555;">Estimado/a <strong>{user_name}</strong>,</p>
      <p style="color: #555;">Gracias por registrarse en <strong>DoxAI</strong>. Para completar el proceso, active su cuenta haciendo clic en el siguiente botón:</p>
      <p style="text-align: center; margin: 25px 0;">
        <a href="{activation_link}" style="display: inline-block; background-color: #4A6CF7; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: 600;">Activar mi cuenta</a>
      </p>
      <div style="background-color: #f0f4ff; border-left: 4px solid #4A6CF7; padding: 15px; margin: 20px 0; border-radius: 4px;">
        <strong>Créditos de bienvenida</strong><br>
        Al activar su cuenta, se le asignarán automáticamente <strong>5 créditos gratuitos</strong>.
      </div>
      <div style="font-size: 14px; color: #d97706; background-color: #fef3c7; padding: 12px; border-radius: 4px; margin: 20px 0; border-left: 4px solid #f59e0b;">
        <strong>Importante:</strong> Este enlace expirará en <strong>60 minutos</strong>.
      </div>
      <p style="color: #555; margin-top: 30px;">Si usted no solicitó la creación de esta cuenta, puede ignorar este mensaje.</p>
      <p style="color: #555;">Atentamente,<br>El equipo de DoxAI</p>
    </div>
    <div style="background-color: #f9f9f9; text-align: center; font-size: 12px; color: #666; padding: 20px; border-top: 1px solid #e5e5e5;">
      <p>Este es un correo automático, por favor no responda a esta dirección.</p>
      <p>&copy; 2025 DoxAI. Todos los derechos reservados.</p>
    </div>
  </div>
</body>
</html>"""
            else:
                html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
  <h2>Bienvenido a DoxAI, {user_name}</h2>
  <p>Gracias por registrarse. Su cuenta ha sido creada.</p>
  <p>Por favor contacte a soporte si necesita activar su cuenta manualmente.</p>
  <hr>
  <p style="color: #666; font-size: 12px;">DoxAI © 2025 – JUVARE®</p>
</body>
</html>"""

        if activation_link:
            text = f"""Estimado/a {user_name},

Gracias por registrarse en DoxAI. Para completar el proceso de activación, utilice el siguiente enlace:

{activation_link}

CRÉDITOS DE BIENVENIDA
Al activar su cuenta, se le asignarán automáticamente 5 créditos gratuitos para que explore las funcionalidades de DoxAI.

IMPORTANTE: Este enlace expirará en 60 minutos. Si no activa su cuenta antes de ese tiempo, deberá solicitar un nuevo enlace de activación.

Si usted no solicitó la creación de esta cuenta, puede ignorar este mensaje.

Atentamente,
El equipo de DoxAI

---
DoxAI © 2025 – JUVARE®
Este es un correo automático, por favor no responda a esta dirección."""
        else:
            text = f"Estimado/a {user_name}, gracias por registrarse en DoxAI. Contacte a soporte para activar su cuenta."

        return html, text, used_template

    def _build_password_reset_body(self, full_name: str, reset_token: str) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de reset de contraseña."""
        template = self._load_template("password_reset_email.html")
        used_template = template is not None

        reset_link = ""
        if self.frontend_url:
            reset_link = f"{self.frontend_url}/auth/reset-password?token={reset_token}"

        if template:
            html = template.replace("{{full_name}}", full_name or "Usuario")
            html = html.replace("{{reset_token}}", reset_token)
            html = html.replace("{{reset_link}}", reset_link)
        else:
            link_html = f'<p><a href="{reset_link}">Restablecer contraseña</a></p>' if reset_link else ""
            html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
  <h2>Restablecer contraseña</h2>
  <p>Hola {full_name or 'Usuario'},</p>
  <p>Recibimos una solicitud para restablecer su contraseña. Use el siguiente código:</p>
  <p style="font-size: 24px; font-weight: bold; color: #4F46E5;">{reset_token}</p>
  {link_html}
  <p>Si no solicitó este cambio, puede ignorar este correo.</p>
  <p>Este código expira en 1 hora.</p>
  <hr>
  <p style="color: #666; font-size: 12px;">DoxAI © 2025 – JUVARE®</p>
</body>
</html>"""

        text = f"Hola {full_name or 'Usuario'}, su código de restablecimiento es: {reset_token}"
        if reset_link:
            text += f"\nO visite: {reset_link}"

        return html, text, used_template

    def _build_welcome_body(self, full_name: str, credits_assigned: int) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de bienvenida."""
        template = self._load_template("welcome_email.html")
        used_template = template is not None

        user_name = full_name or "Usuario"
        frontend_url = self.frontend_url or ""

        if template:
            html = template.replace("{{ user_name }}", user_name).replace("{{user_name}}", user_name)
            html = html.replace("{{ frontend_url }}", frontend_url).replace("{{frontend_url}}", frontend_url)
            html = html.replace("{{ credits_assigned }}", str(credits_assigned)).replace("{{credits_assigned}}", str(credits_assigned))
        else:
            login_link = (
                f'<a href="{frontend_url}" style="display: inline-block; background-color: #4A6CF7; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; font-weight: bold;">Iniciar sesión</a>'
                if frontend_url else ""
            )
            html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
  <h2>Bienvenido a DoxAI, {user_name}</h2>
  <p>Su cuenta ha sido activada exitosamente.</p>
  <p style="background-color: #f0f4ff; border-left: 4px solid #4A6CF7; padding: 15px; margin: 20px 0;">
    <strong>Créditos de bienvenida</strong><br>
    Hemos acreditado <strong>{credits_assigned} créditos gratuitos</strong> a su cuenta.
  </p>
  <p style="text-align: center;">{login_link}</p>
  <p>Gracias por elegir DoxAI.</p>
  <hr>
  <p style="color: #666; font-size: 12px;">DoxAI © 2025 – JUVARE®</p>
</body>
</html>"""

        text = f"Estimado/a {user_name}, bienvenido a DoxAI. Su cuenta ha sido activada y se le asignaron {credits_assigned} créditos gratuitos."
        if frontend_url:
            text += f" Inicie sesión aquí: {frontend_url}"

        return html, text, used_template

    def build_email_message(self, to_email: str, subject: str, html_body: str, text_body: str) -> EmailMessage:
        """Construye EmailMessage con headers robustos para entregabilidad."""
        msg = EmailMessage()

        msg["From"] = formataddr((self.from_name, self.from_email))
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)

        domain = self.from_email.split("@")[-1] if "@" in self.from_email else "doxai.local"
        msg["Message-ID"] = make_msgid(domain=domain)

        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        return msg

    def _send_sync(self, to_email: str, subject: str, html_body: str, text_body: str) -> str:
        """Envío síncrono por SMTP. Retorna Message-ID."""
        msg = self.build_email_message(to_email, subject, html_body, text_body)

        logger.info(
            "[SMTP] preparing email: to=%s subject=%s from=%s via=%s:%s ssl=%s tls=%s",
            to_email, subject, self.from_email, self.server, self.port, self.use_ssl, self.use_tls,
        )
        logger.debug(
            "[SMTP] email sizes: text_plain=%d bytes, text_html=%d bytes",
            len(text_body.encode("utf-8")), len(html_body.encode("utf-8")),
        )
        logger.debug("[SMTP] headers: Date=%s Message-ID=%s", msg.get("Date"), msg.get("Message-ID"))

        smtp_debug = os.getenv("EMAIL_SMTP_DEBUG", "false").lower() == "true"

        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.server, self.port, context=context, timeout=self.timeout) as server:
                    if smtp_debug:
                        server.set_debuglevel(1)
                        logger.debug("[SMTP] debug mode enabled (EMAIL_SMTP_DEBUG=true)")
                    server.login(self.username, self.password)
                    refused = server.send_message(msg)
                    msg_id = msg.get("Message-ID", "unknown")
                    if refused:
                        logger.warning("[SMTP] refused recipients: %s", refused)
                    else:
                        logger.info("[SMTP] send_message accepted by server (no refused recipients)")
                    logger.info("[SMTP] sent ok to=%s msg_id=%s", to_email, msg_id)
                    return msg_id
            else:
                with smtplib.SMTP(self.server, self.port, timeout=self.timeout) as server:
                    if smtp_debug:
                        server.set_debuglevel(1)
                        logger.debug("[SMTP] debug mode enabled (EMAIL_SMTP_DEBUG=true)")
                    server.ehlo()
                    if self.use_tls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                        server.ehlo()
                    server.login(self.username, self.password)
                    refused = server.send_message(msg)
                    msg_id = msg.get("Message-ID", "unknown")
                    if refused:
                        logger.warning("[SMTP] refused recipients: %s", refused)
                    else:
                        logger.info("[SMTP] send_message accepted by server (no refused recipients)")
                    logger.info("[SMTP] sent ok to=%s msg_id=%s ssl=%s tls=%s", to_email, msg_id, self.use_ssl, self.use_tls)
                    return msg_id

        except Exception:
            logger.exception("[SMTP] send failed to=%s", to_email)
            raise

    async def send_activation_email(self, to_email: str, full_name: str, activation_token: str) -> None:
        """Envía email de activación de cuenta."""
        html, text, used_template = self._build_activation_body(full_name, activation_token)

        logger.info(
            "[SMTP] activation email: to=%s user=%s token=%s template=%s",
            to_email,
            full_name or "Usuario",
            self._mask_token(activation_token),
            "loaded" if used_template else "fallback",
        )

        await asyncio.to_thread(self._send_sync, to_email, "Active su cuenta en DoxAI", html, text)

    async def send_password_reset_email(self, to_email: str, full_name: str, reset_token: str) -> None:
        """Envía email de reset de contraseña."""
        html, text, used_template = self._build_password_reset_body(full_name, reset_token)

        logger.info(
            "[SMTP] password reset email: to=%s user=%s token=%s template=%s",
            to_email,
            full_name or "Usuario",
            self._mask_token(reset_token),
            "loaded" if used_template else "fallback",
        )

        await asyncio.to_thread(self._send_sync, to_email, "Restablecer contraseña - DoxAI", html, text)

    async def send_welcome_email(self, to_email: str, full_name: str, credits_assigned: int) -> None:
        """Envía email de bienvenida."""
        html, text, used_template = self._build_welcome_body(full_name, credits_assigned)

        logger.info(
            "[SMTP] welcome email: to=%s user=%s credits=%d template=%s",
            to_email,
            full_name or "Usuario",
            credits_assigned,
            "loaded" if used_template else "fallback",
        )

        await asyncio.to_thread(self._send_sync, to_email, "Bienvenido a DoxAI", html, text)


# Fin del script smtp_email_sender.py