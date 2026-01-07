# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/mailersend_email_sender.py

Implementación de envío de correos usando MailerSend API.
Usa templates de templates/emails/ como fuente de verdad.

Autor: Ixchel Beristain
Creado: 2025-12-16
Actualizado: 2026-01-02 - Instrumentación de eventos para métricas

Notas:
- MailerSend API es más confiable que SMTP en entornos cloud (Railway, Vercel).
- No requiere TLS cert validation del sistema operativo.
- Soporta tracking de emails y webhooks (no implementados aquí).
- Cada envío registra evento en auth_email_events para métricas.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional, Tuple, TYPE_CHECKING

import httpx

from app.shared.integrations.email_templates import (
    render_email,
    mask_token,
    get_fallback_text,
)

if TYPE_CHECKING:
    from app.shared.config.settings_base import BaseAppSettings
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Flag to log factory validation warning only once per process
_factory_warning_logged = False

# MailerSend API endpoint
MAILERSEND_API_URL = "https://api.mailersend.com/v1/email"


class MailerSendError(Exception):
    """Error de MailerSend con código interno (no expone detalles del provider)."""
    
    def __init__(self, error_code: str, status_code: int, message: str):
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)


def _normalize_base_url(url: Optional[str]) -> Optional[str]:
    """Normaliza una URL base (quita espacios y slash final)."""
    if not url:
        return None
    u = url.strip()
    return u.rstrip("/") if u else None


class MailerSendEmailSender:
    """Envío de correos usando MailerSend API con instrumentación de eventos."""

    def __init__(
        self,
        api_key: str,
        from_email: str,
        from_name: str = "DoxAI",
        timeout: int = 30,
        frontend_url: Optional[str] = None,
        support_email: Optional[str] = None,
        db_session: Optional["AsyncSession"] = None,
        event_session_factory: Optional["async_sessionmaker[AsyncSession]"] = None,
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
        self.support_email = support_email or "soporte@doxai.site"
        self._db_session = db_session  # Legacy, kept for backwards compatibility
        self._event_session_factory = event_session_factory  # async_sessionmaker for event logging

    # ─────────────────────────────────────────────────────────────────────────
    # Event Logging Helpers (for auth_email_events metrics)
    # ─────────────────────────────────────────────────────────────────────────
    
    @staticmethod
    def _generate_idempotency_key(email_type: str, to_email: str, unique_context: str) -> str:
        """
        Generate a stable idempotency key for deduplication.
        
        Args:
            email_type: Type of email (account_activation, welcome, etc.)
            to_email: Recipient email
            unique_context: Additional unique context (e.g., token hash)
            
        Returns:
            SHA-256 hash truncated to 64 chars
        """
        raw = f"{email_type}:{to_email}:{unique_context}"
        return hashlib.sha256(raw.encode()).hexdigest()[:64]
    
    @staticmethod
    def _extract_domain(email: str) -> Optional[str]:
        """Extract domain from email (no PII)."""
        if not email or "@" not in email:
            return None
        try:
            return email.split("@")[1].lower().strip()
        except (IndexError, AttributeError):
            return None
    
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

    async def _log_email_event(
        self,
        *,
        email_type: str,
        status: str,
        to_email: str,
        user_id: Optional[int] = None,
        provider_message_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> None:
        """
        Log email event to auth_email_events table using a SEPARATE session.
        
        Uses SessionLocal (async_sessionmaker) to create an independent session
        so that rollback in the main flow does NOT lose email event logs.
        This is critical for metrics.
        
        Silently fails if no session factory or on error (doesn't block email sending).
        """
        session_factory = self._get_event_session_factory()
        if session_factory is None:
            # Warning already logged by _get_event_session_factory (once per process)
            logger.warning(
                "auth_email_event_insert_skipped: no session_factory type=%s status=%s",
                email_type,
                status,
            )
            return
        
        # Log intent to insert (for debugging in Railway)
        logger.info(
            "auth_email_event_insert_started: type=%s status=%s user_id=%s domain=%s",
            email_type,
            status,
            user_id,
            self._extract_domain(to_email),
        )
        
        try:
            from sqlalchemy import text
            
            # Use SessionLocal (async_sessionmaker) to create independent session
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
                        updated_at
                    ) VALUES (
                        CAST(:email_type AS public.auth_email_type),
                        CAST(:status AS public.auth_email_event_status),
                        :recipient_domain,
                        :user_id,
                        'mailersend',
                        :provider_message_id,
                        :latency_ms,
                        :error_code,
                        :error_message,
                        :idempotency_key,
                        CASE WHEN :status_check != 'pending' THEN now() ELSE NULL END
                    )
                    ON CONFLICT (idempotency_key)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        provider_message_id = COALESCE(EXCLUDED.provider_message_id, auth_email_events.provider_message_id),
                        latency_ms = COALESCE(EXCLUDED.latency_ms, auth_email_events.latency_ms),
                        error_code = COALESCE(EXCLUDED.error_code, auth_email_events.error_code),
                        error_message = COALESCE(EXCLUDED.error_message, auth_email_events.error_message),
                        updated_at = now()
                    RETURNING event_id
                """)
                
                result = await log_session.execute(q, {
                    "email_type": email_type,
                    "status": status,
                    "status_check": status,  # Separate param for CASE statement
                    "recipient_domain": self._extract_domain(to_email),
                    "user_id": user_id,
                    "provider_message_id": provider_message_id,
                    "latency_ms": latency_ms,
                    "error_code": error_code,
                    "error_message": (error_message or "")[:500] if error_message else None,
                    "idempotency_key": idempotency_key,
                })
                
                row = result.first()
                event_id = row[0] if row else None
                
                # Commit in the separate session - isolated from main transaction
                await log_session.commit()
            
            logger.info(
                "auth_email_event_insert_success: event_id=%s type=%s status=%s latency_ms=%s",
                event_id,
                email_type,
                status,
                latency_ms,
            )
            
        except Exception as e:
            # Don't fail email sending due to logging errors - but log the failure
            logger.exception(
                "auth_email_event_insert_failed: type=%s status=%s error=%s",
                email_type,
                status,
                str(e),
            )

    @classmethod
    def from_settings(
        cls,
        settings: "BaseAppSettings",
        db_session: Optional["AsyncSession"] = None,
        event_session_factory: Optional["async_sessionmaker[AsyncSession]"] = None,
    ) -> "MailerSendEmailSender":
        """
        Crea instancia desde settings (fuente de verdad).
        
        Args:
            settings: Configuración de la aplicación
            db_session: Sesión de base de datos (legacy, para compatibilidad)
            event_session_factory: async_sessionmaker para logging de eventos.
                Si no se provee, usa SessionLocal de database.py.
            
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

        support_email = getattr(settings, "support_email", None) or "soporte@doxai.site"

        logger.info(
            "[MailerSend] config: from=%s (%s) reply_to=%s timeout=%ss event_logging=%s",
            from_email,
            from_name,
            support_email,
            timeout,
            "factory" if event_session_factory else ("db_session" if db_session else "auto"),
        )

        return cls(
            api_key=api_key,
            from_email=from_email,
            from_name=from_name,
            timeout=timeout,
            frontend_url=frontend_url,
            support_email=support_email,
            db_session=db_session,
            event_session_factory=event_session_factory,
        )

    @classmethod
    def from_env(cls) -> "MailerSendEmailSender":
        """
        Wrapper de compatibilidad: carga settings y delega a from_settings().
        Preferir from_settings() para mejor testabilidad.
        """
        from app.shared.config import settings
        return cls.from_settings(settings)

    def _classify_mailersend_error(self, status_code: int, error_body: str) -> str:
        """
        Clasifica errores de MailerSend a códigos internos.
        
        No expone detalles del provider al cliente.
        
        Returns:
            Código interno seguro para logs/métricas.
        """
        error_lower = error_body.lower()
        
        # Trial account unique recipients limit (#MS42225)
        if status_code == 422 and "#ms42225" in error_lower:
            return "mailersend_trial_unique_recipients_limit"
        
        # Trial account sending limit
        if status_code == 422 and "trial" in error_lower and "limit" in error_lower:
            return "mailersend_trial_limit"
        
        # Rate limiting
        if status_code == 429:
            return "mailersend_rate_limit"
        
        # Authentication errors
        if status_code == 401:
            return "mailersend_auth_error"
        
        # Validation errors (other 422)
        if status_code == 422:
            return "mailersend_validation_error"
        
        # Server errors
        if status_code >= 500:
            return "mailersend_server_error"
        
        # Generic client error
        if status_code >= 400:
            return "mailersend_client_error"
        
        return "mailersend_unknown_error"

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
            "reply_to": {
                "email": self.support_email,
                "name": "Soporte DoxAI",
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

                # Handle errors - classify and log appropriately
                error_body = response.text
                content_type = response.headers.get("Content-Type", "")
                error_code = self._classify_mailersend_error(
                    response.status_code, error_body
                )
                
                if "application/json" in content_type:
                    try:
                        error_json = response.json()
                        logger.warning(
                            "[MailerSend] send failed: to=%s status=%d error_code=%s json=%s",
                            to_email,
                            response.status_code,
                            error_code,
                            error_json,
                        )
                    except Exception:
                        logger.warning(
                            "[MailerSend] send failed: to=%s status=%d error_code=%s body=%s",
                            to_email,
                            response.status_code,
                            error_code,
                            error_body[:500],
                        )
                else:
                    logger.warning(
                        "[MailerSend] send failed: to=%s status=%d error_code=%s body=%s",
                        to_email,
                        response.status_code,
                        error_code,
                        error_body[:500],
                    )

                # Raise with internal error_code, NOT provider details
                raise MailerSendError(
                    error_code=error_code,
                    status_code=response.status_code,
                    message=f"Error de envío de email (código: {error_code})",
                )

            except httpx.TimeoutException as e:
                logger.error("[MailerSend] timeout: to=%s error=%s", to_email, str(e))
                raise RuntimeError(f"MailerSend timeout: {e}") from e
            except httpx.RequestError as e:
                logger.error("[MailerSend] request error: to=%s error=%s", to_email, str(e))
                raise RuntimeError(f"MailerSend request error: {e}") from e

    async def send_activation_email(
        self, to_email: str, full_name: str, activation_token: str,
        user_id: Optional[int] = None,
    ) -> None:
        """Envía email de activación de cuenta con instrumentación."""
        email_type = "account_activation"
        idempotency_key = self._generate_idempotency_key(
            email_type, to_email, hashlib.sha256(activation_token.encode()).hexdigest()[:16]
        )
        
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

        # Log pending event
        await self._log_email_event(
            email_type=email_type,
            status="pending",
            to_email=to_email,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        
        start_time = time.perf_counter()
        try:
            message_id = await self._send_email(to_email, "Active su cuenta en DoxAI", html, text)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Log sent event
            await self._log_email_event(
                email_type=email_type,
                status="sent",
                to_email=to_email,
                user_id=user_id,
                provider_message_id=message_id,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_code = getattr(e, "error_code", "unknown_error")
            
            # Log failed event
            await self._log_email_event(
                email_type=email_type,
                status="failed",
                to_email=to_email,
                user_id=user_id,
                latency_ms=latency_ms,
                error_code=str(error_code),
                error_message=str(e)[:500],
                idempotency_key=idempotency_key,
            )
            raise

    async def send_password_reset_email(
        self, to_email: str, full_name: str, reset_token: str,
        user_id: Optional[int] = None,
    ) -> None:
        """Envía email de reset de contraseña con instrumentación."""
        email_type = "password_reset_request"
        idempotency_key = self._generate_idempotency_key(
            email_type, to_email, hashlib.sha256(reset_token.encode()).hexdigest()[:16]
        )
        
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

        # Log pending event
        await self._log_email_event(
            email_type=email_type,
            status="pending",
            to_email=to_email,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        
        start_time = time.perf_counter()
        try:
            message_id = await self._send_email(to_email, "Restablecer contraseña - DoxAI", html, text)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Log sent event
            await self._log_email_event(
                email_type=email_type,
                status="sent",
                to_email=to_email,
                user_id=user_id,
                provider_message_id=message_id,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_code = getattr(e, "error_code", "unknown_error")
            
            # Log failed event
            await self._log_email_event(
                email_type=email_type,
                status="failed",
                to_email=to_email,
                user_id=user_id,
                latency_ms=latency_ms,
                error_code=str(error_code),
                error_message=str(e)[:500],
                idempotency_key=idempotency_key,
            )
            raise

    async def send_welcome_email(
        self, to_email: str, full_name: str, credits_assigned: int,
        user_id: Optional[int] = None,
    ) -> None:
        """Envía email de bienvenida con instrumentación."""
        email_type = "welcome"
        # For welcome emails, use user_id as unique context (no token)
        idempotency_key = self._generate_idempotency_key(
            email_type, to_email, str(user_id or "no_user_id")
        )
        
        html, text, used_template = self._build_welcome_body(full_name, credits_assigned)

        logger.info(
            "[MailerSend] welcome email: to=%s user=%s credits=%d template=%s",
            to_email,
            full_name or "Usuario",
            credits_assigned,
            "loaded" if used_template else "fallback",
        )

        # Log pending event
        await self._log_email_event(
            email_type=email_type,
            status="pending",
            to_email=to_email,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        
        start_time = time.perf_counter()
        try:
            message_id = await self._send_email(to_email, "Bienvenido a DoxAI", html, text)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Log sent event
            await self._log_email_event(
                email_type=email_type,
                status="sent",
                to_email=to_email,
                user_id=user_id,
                provider_message_id=message_id,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_code = getattr(e, "error_code", "unknown_error")
            
            # Log failed event
            await self._log_email_event(
                email_type=email_type,
                status="failed",
                to_email=to_email,
                user_id=user_id,
                latency_ms=latency_ms,
                error_code=str(error_code),
                error_message=str(e)[:500],
                idempotency_key=idempotency_key,
            )
            raise

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
            "[MailerSend] admin activation notice: to=%s user=%s user_id=%s template=%s",
            to_email,
            user_email[:3] + "***" if user_email else "unknown",
            user_id,
            "loaded" if used_template else "fallback",
        )

        await self._send_email(
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
        user_id: Optional[int] = None,
    ) -> None:
        """
        Envía notificación al usuario cuando su contraseña fue restablecida.
        
        Args:
            to_email: Email del usuario
            full_name: Nombre del usuario
            ip_address: IP desde donde se hizo el reset (opcional)
            user_agent: User agent del navegador (opcional)
            reset_datetime_utc: Fecha/hora del reset (opcional, default=now)
            user_id: ID del usuario (opcional, para métricas)
        """
        from datetime import datetime, timezone as tz
        
        email_type = "password_reset_success"
        
        # Stabilize reset_datetime_utc at the start for consistent idempotency_key
        if not reset_datetime_utc:
            reset_datetime_utc = datetime.now(tz.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        idempotency_key = self._generate_idempotency_key(
            email_type, to_email, reset_datetime_utc
        )
        
        html, text, used_template = self._build_password_reset_success_body(
            full_name=full_name,
            ip_address=ip_address,
            user_agent=user_agent,
            reset_datetime_utc=reset_datetime_utc,
        )

        logger.info(
            "[MailerSend] password_reset_success: to=%s template=%s",
            to_email[:3] + "***" if to_email else "unknown",
            "loaded" if used_template else "fallback",
        )

        # Log pending event
        await self._log_email_event(
            email_type=email_type,
            status="pending",
            to_email=to_email,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        
        start_time = time.perf_counter()
        try:
            message_id = await self._send_email(
                to_email,
                "Su contraseña fue restablecida - DoxAI",
                html,
                text,
            )
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            # Log sent event
            await self._log_email_event(
                email_type=email_type,
                status="sent",
                to_email=to_email,
                user_id=user_id,
                provider_message_id=message_id,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            error_code = getattr(e, "error_code", "unknown_error")
            
            # Log failed event
            await self._log_email_event(
                email_type=email_type,
                status="failed",
                to_email=to_email,
                user_id=user_id,
                latency_ms=latency_ms,
                error_code=str(error_code),
                error_message=str(e)[:500],
                idempotency_key=idempotency_key,
            )
            raise


# Fin del archivo backend/app/shared/integrations/mailersend_email_sender.py
