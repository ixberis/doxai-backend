# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/mailersend_email_sender.py

Implementación de envío de correos usando MailerSend API.
Usa templates de templates/emails/ como fuente de verdad.

Autor: Ixchel Beristain
Creado: 2025-12-16
Actualizado: 2026-01-02 - Instrumentación de eventos para métricas
Actualizado: 2026-01-09 - Canon SSOT (auth_user_id), no PII, idempotencia estable, _send_email restaurado

Notas:
- MailerSend API es más confiable que SMTP en entornos cloud (Railway, Vercel).
- No requiere TLS cert validation del sistema operativo.
- Soporta tracking de emails y webhooks (webhooks se implementan en routes/webhooks_routes.py).
- Cada envío registra evento en auth_email_events para métricas (sin PII: solo dominio).
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Optional, Tuple, TYPE_CHECKING, Dict, Any
from uuid import UUID

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

        # Legacy (no usar para logging de eventos, pero lo conservamos por compatibilidad)
        self._db_session = db_session

        # async_sessionmaker para logging de eventos (aislado)
        self._event_session_factory = event_session_factory

    # ─────────────────────────────────────────────────────────────────────────
    # Event Logging Helpers (for auth_email_events metrics)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _generate_idempotency_key(
        email_type: str,
        auth_user_id: Optional[UUID],
        unique_context: str,
    ) -> str:
        """
        Generate a stable idempotency key for deduplication.

        Canon (DB 2.0): {email_type}:{auth_user_id}:{context} (no PII).
        If auth_user_id is None, falls back to a hash-only key.

        Returns:
            SHA-256 hash truncated to 64 chars
        """
        raw = f"{email_type}:{str(auth_user_id) if auth_user_id else 'no_auth_user_id'}:{unique_context}"
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
            if not callable(self._event_session_factory):
                if not _factory_warning_logged:
                    logger.warning(
                        "email_event_log_skipped_invalid_factory: event_session_factory is not callable"
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
                    str(e),
                )
                _factory_warning_logged = True
            return None

    async def _log_email_event(
        self,
        *,
        email_type: str,
        status: str,
        to_email: str,
        auth_user_id: Optional[UUID] = None,
        provider_message_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Log email event to auth_email_events table using a SEPARATE session.

        DB 2.0: Persist by SSOT auth_user_id (no user_id legacy).
        
        IMPORTANTE: Normaliza email_type a valor canónico SQL antes de INSERT.
        Acepta aliases legacy (account_activation → activation).

        Silently fails if no session factory or on error (doesn't block email sending).
        """
        # Normalizar email_type a valor canónico SQL
        try:
            from app.modules.auth.enums import normalize_email_type
            canonical_email_type = normalize_email_type(email_type)
        except ValueError as e:
            logger.error("auth_email_event_insert_invalid_type: %s", str(e))
            return
        except ImportError:
            # Fallback si no se puede importar (edge case)
            canonical_email_type = email_type
        
        session_factory = self._get_event_session_factory()
        if session_factory is None:
            logger.warning(
                "auth_email_event_insert_skipped: no session_factory type=%s status=%s",
                canonical_email_type,
                status,
            )
            return

        logger.info(
            "auth_email_event_insert_started: type=%s status=%s auth_user_id=%s domain=%s",
            canonical_email_type,
            status,
            (str(auth_user_id)[:8] + "...") if auth_user_id else None,
            self._extract_domain(to_email),
        )

        try:
            from sqlalchemy import text

            async with session_factory() as log_session:
                q = text(
                    """
                    INSERT INTO public.auth_email_events (
                        email_type,
                        status,
                        recipient_domain,
                        auth_user_id,
                        provider,
                        provider_message_id,
                        latency_ms,
                        error_code,
                        error_message,
                        idempotency_key,
                        correlation_id,
                        updated_at
                    ) VALUES (
                        CAST(:email_type AS public.auth_email_type),
                        CAST(:status AS public.auth_email_event_status),
                        :recipient_domain,
                        :auth_user_id,
                        'mailersend',
                        :provider_message_id,
                        :latency_ms,
                        :error_code,
                        :error_message,
                        :idempotency_key,
                        :correlation_id,
                        CASE WHEN :status_check != 'pending' THEN now() ELSE NULL END
                    )
                    ON CONFLICT (idempotency_key)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        provider_message_id = COALESCE(EXCLUDED.provider_message_id, auth_email_events.provider_message_id),
                        latency_ms = COALESCE(EXCLUDED.latency_ms, auth_email_events.latency_ms),
                        error_code = COALESCE(EXCLUDED.error_code, auth_email_events.error_code),
                        error_message = COALESCE(EXCLUDED.error_message, auth_email_events.error_message),
                        correlation_id = COALESCE(EXCLUDED.correlation_id, auth_email_events.correlation_id),
                        updated_at = now()
                    RETURNING event_id
                    """
                )

                result = await log_session.execute(
                    q,
                    {
                        "email_type": canonical_email_type,  # Usar valor normalizado
                        "status": status,
                        "status_check": status,
                        "recipient_domain": self._extract_domain(to_email),
                        "auth_user_id": str(auth_user_id) if auth_user_id else None,
                        "provider_message_id": provider_message_id,
                        "latency_ms": latency_ms,
                        "error_code": error_code,
                        "error_message": (error_message or "")[:500] if error_message else None,
                        "idempotency_key": idempotency_key,
                        "correlation_id": correlation_id,
                    },
                )

                row = result.first()
                event_id = row[0] if row else None
                await log_session.commit()

            logger.info(
                "auth_email_event_insert_success: event_id=%s type=%s status=%s latency_ms=%s",
                event_id,
                canonical_email_type,  # Log valor canónico
                status,
                latency_ms,
            )

        except Exception as e:
            logger.exception(
                "auth_email_event_insert_failed: type=%s status=%s error=%s",
                email_type,
                status,
                str(e),
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Settings factory
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_settings(
        cls,
        settings: "BaseAppSettings",
        db_session: Optional["AsyncSession"] = None,
        event_session_factory: Optional["async_sessionmaker[AsyncSession]"] = None,
    ) -> "MailerSendEmailSender":
        """Crea instancia desde settings (fuente de verdad)."""
        api_key = ""
        if getattr(settings, "mailersend_api_key", None):
            api_key = settings.mailersend_api_key.get_secret_value().strip()

        from_email = (getattr(settings, "mailersend_from_email", None) or "").strip()
        from_name = (getattr(settings, "mailersend_from_name", None) or "DoxAI").strip()
        timeout = getattr(settings, "email_timeout_sec", None) or 30

        frontend_url = _normalize_base_url(
            getattr(settings, "frontend_base_url", None) or getattr(settings, "frontend_url", None)
        )

        if not api_key:
            raise ValueError(
                "[MailerSend] MAILERSEND_API_KEY es requerido. Configúrelo en Railway/Vercel."
            )
        if not from_email:
            raise ValueError(
                "[MailerSend] MAILERSEND_FROM_EMAIL es requerido. Configúrelo en Railway/Vercel."
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
        from app.shared.config import settings
        return cls.from_settings(settings)

    # ─────────────────────────────────────────────────────────────────────────
    # MailerSend error classification
    # ─────────────────────────────────────────────────────────────────────────

    def _classify_mailersend_error(self, status_code: int, error_body: str) -> str:
        """
        Clasifica errores de MailerSend a códigos internos.

        No expone detalles del provider al cliente.
        """
        error_lower = (error_body or "").lower()

        if status_code == 422 and "#ms42225" in error_lower:
            return "mailersend_trial_unique_recipients_limit"

        if status_code == 422 and "trial" in error_lower and "limit" in error_lower:
            return "mailersend_trial_limit"

        if status_code == 429:
            return "mailersend_rate_limit"

        if status_code == 401:
            return "mailersend_auth_error"

        if status_code == 422:
            return "mailersend_validation_error"

        if status_code >= 500:
            return "mailersend_server_error"

        if status_code >= 400:
            return "mailersend_client_error"

        return "mailersend_unknown_error"

    # ─────────────────────────────────────────────────────────────────────────
    # Template builders
    # ─────────────────────────────────────────────────────────────────────────

    def _build_activation_body(self, full_name: str, activation_token: str) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de activación."""
        user_name = full_name or "Usuario"
        activation_link = ""
        if self.frontend_url:
            activation_link = f"{self.frontend_url}/auth/activate?token={activation_token}"

        context: Dict[str, Any] = {
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

    def _build_password_reset_body(self, full_name: str, reset_token: str) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de reset de contraseña."""
        user_name = full_name or "Usuario"
        reset_link = ""
        if self.frontend_url:
            reset_link = f"{self.frontend_url}/auth/reset-password?token={reset_token}"

        context: Dict[str, Any] = {
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

    def _build_welcome_body(self, full_name: str, credits_assigned: int) -> Tuple[str, str, bool]:
        """Construye cuerpo para email de bienvenida."""
        user_name = full_name or "Usuario"
        context: Dict[str, Any] = {
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

        context: Dict[str, Any] = {
            "user_email": user_email,
            "user_name": user_name or "No especificado",
            "user_id": str(user_id),
            "activation_datetime": activation_datetime_utc,
            "credits_assigned": str(credits_assigned),
            "ip_address": ip_address or "No disponible",
            "user_agent": (user_agent or "No disponible")[:200],
        }

        html, text, used_template = render_email("admin_activation_notice", context)

        if not text:
            text = (
                "NUEVA CUENTA ACTIVADA - DoxAI\n"
                "==============================\n\n"
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

        context: Dict[str, Any] = {
            "user_name": full_name or "Usuario",
            "reset_datetime": reset_datetime_utc,
            "ip_address": ip_address or "No disponible",
            "user_agent": (user_agent or "No disponible")[:200],
            "login_url": login_url,
            "frontend_url": self.frontend_url or "",
            "support_email": self.support_email,
        }

        html, text, used_template = render_email("password_reset_success_email", context)

        if not text:
            text = (
                "CONTRASEÑA RESTABLECIDA - DoxAI\n"
                "================================\n\n"
                f"Hola {full_name or 'Usuario'},\n\n"
                "Su contraseña ha sido restablecida exitosamente.\n\n"
                f"Fecha/Hora: {reset_datetime_utc} UTC\n"
                f"IP: {ip_address or 'No disponible'}\n\n"
                f"Si usted no realizó este cambio, contacte soporte: {self.support_email}\n"
            )

        if not html:
            html = f"<pre>{text}</pre>"

        return html, text, used_template

    # ─────────────────────────────────────────────────────────────────────────
    # Core sender (this MUST exist for tests to patch it)
    # ─────────────────────────────────────────────────────────────────────────

    async def _send_email(self, to_email: str, subject: str, html_body: str, text_body: str) -> str:
        """
        Envía email via MailerSend API. Retorna message_id.

        IMPORTANT: Este método existe para:
        - centralizar el POST a MailerSend
        - permitir patch en tests (instrumentation)
        """
        payload = {
            "from": {"email": self.from_email, "name": self.from_name},
            "reply_to": {"email": self.support_email, "name": "Soporte DoxAI"},
            "to": [{"email": to_email}],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info("[MailerSend] sending: to=%s subject=%s from=%s", to_email, subject, self.from_email)

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
                    logger.info("[MailerSend] sent ok: to=%s message_id=%s", to_email, message_id)
                    return message_id

                error_body = response.text
                content_type = response.headers.get("Content-Type", "")
                error_code = self._classify_mailersend_error(response.status_code, error_body)

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
                            (error_body or "")[:500],
                        )
                else:
                    logger.warning(
                        "[MailerSend] send failed: to=%s status=%d error_code=%s body=%s",
                        to_email,
                        response.status_code,
                        error_code,
                        (error_body or "")[:500],
                    )

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

    # ─────────────────────────────────────────────────────────────────────────
    # Public API: send_* methods (instrumented)
    # ─────────────────────────────────────────────────────────────────────────

    async def send_activation_email(
        self,
        to_email: str,
        full_name: str,
        activation_token: str,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        user_id: Optional[int] = None,  # legacy param kept for callsites/tests (not persisted)
    ) -> None:
        """Envía email de activación de cuenta con instrumentación (SSOT auth_user_id)."""
        email_type = "account_activation"
        token_ctx = hashlib.sha256(activation_token.encode()).hexdigest()[:16]
        idempotency_key = self._generate_idempotency_key(email_type, auth_user_id, token_ctx)

        html, text, used_template = self._build_activation_body(full_name, activation_token)

        logger.info(
            "[MailerSend] activation email: to=%s user=%s token=%s template=%s",
            to_email,
            full_name or "Usuario",
            mask_token(activation_token),
            "loaded" if used_template else "fallback",
        )

        await self._log_email_event(
            email_type=email_type,
            status="pending",
            to_email=to_email,
            auth_user_id=auth_user_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

        start_time = time.perf_counter()
        try:
            message_id = await self._send_email(to_email, "Active su cuenta en DoxAI", html, text)
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            await self._log_email_event(
                email_type=email_type,
                status="sent",
                to_email=to_email,
                auth_user_id=auth_user_id,
                provider_message_id=message_id,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            err_code = getattr(e, "error_code", "unknown_error")

            await self._log_email_event(
                email_type=email_type,
                status="failed",
                to_email=to_email,
                auth_user_id=auth_user_id,
                latency_ms=latency_ms,
                error_code=str(err_code),
                error_message=str(e)[:500],
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
            raise

    async def send_password_reset_email(
        self,
        to_email: str,
        full_name: str,
        reset_token: str,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        user_id: Optional[int] = None,  # legacy param kept (not persisted)
    ) -> None:
        """Envía email de reset de contraseña con instrumentación (SSOT auth_user_id)."""
        email_type = "password_reset_request"
        token_ctx = hashlib.sha256(reset_token.encode()).hexdigest()[:16]
        idempotency_key = self._generate_idempotency_key(email_type, auth_user_id, token_ctx)

        html, text, used_template = self._build_password_reset_body(full_name, reset_token)

        logger.info(
            "[MailerSend] password reset: to=%s user=%s token=%s template=%s",
            to_email,
            full_name or "Usuario",
            mask_token(reset_token),
            "loaded" if used_template else "fallback",
        )

        await self._log_email_event(
            email_type=email_type,
            status="pending",
            to_email=to_email,
            auth_user_id=auth_user_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

        start_time = time.perf_counter()
        try:
            message_id = await self._send_email(to_email, "Restablecer contraseña - DoxAI", html, text)
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            await self._log_email_event(
                email_type=email_type,
                status="sent",
                to_email=to_email,
                auth_user_id=auth_user_id,
                provider_message_id=message_id,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            err_code = getattr(e, "error_code", "unknown_error")

            await self._log_email_event(
                email_type=email_type,
                status="failed",
                to_email=to_email,
                auth_user_id=auth_user_id,
                latency_ms=latency_ms,
                error_code=str(err_code),
                error_message=str(e)[:500],
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
            raise

    async def send_welcome_email(
        self,
        to_email: str,
        full_name: str,
        credits_assigned: int,
        *,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
        user_id: Optional[int] = None,  # legacy param kept (not persisted)
    ) -> None:
        """Envía email de bienvenida con instrumentación (SSOT auth_user_id)."""
        email_type = "welcome"
        ctx = str(credits_assigned)
        idempotency_key = self._generate_idempotency_key(email_type, auth_user_id, ctx)

        html, text, used_template = self._build_welcome_body(full_name, credits_assigned)

        logger.info(
            "[MailerSend] welcome email: to=%s user=%s credits=%d template=%s",
            to_email,
            full_name or "Usuario",
            credits_assigned,
            "loaded" if used_template else "fallback",
        )

        await self._log_email_event(
            email_type=email_type,
            status="pending",
            to_email=to_email,
            auth_user_id=auth_user_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

        start_time = time.perf_counter()
        try:
            message_id = await self._send_email(to_email, "Bienvenido a DoxAI", html, text)
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            await self._log_email_event(
                email_type=email_type,
                status="sent",
                to_email=to_email,
                auth_user_id=auth_user_id,
                provider_message_id=message_id,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            err_code = getattr(e, "error_code", "unknown_error")

            await self._log_email_event(
                email_type=email_type,
                status="failed",
                to_email=to_email,
                auth_user_id=auth_user_id,
                latency_ms=latency_ms,
                error_code=str(err_code),
                error_message=str(e)[:500],
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
            raise

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
        Nota: este correo es operativo/admin; NO se instrumenta en auth_email_events
        (si lo quieres instrumentar, lo podemos meter como email_type=admin_activation_notice
        y agregar el enum).
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
            (user_email[:3] + "***") if user_email else "unknown",
            user_id,
            "loaded" if used_template else "fallback",
        )

        await self._send_email(
            to_email,
            f"Cuenta activada en DoxAI - {user_email}",
            html,
            text,
        )

    async def send_password_reset_success_email(
        self,
        to_email: str,
        *,
        full_name: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reset_datetime_utc: Optional[str] = None,
        auth_user_id: Optional[UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Envía notificación al usuario cuando su contraseña fue restablecida.
        Instrumentado en auth_email_events con email_type=password_reset_success.
        """
        from datetime import datetime, timezone as tz

        email_type = "password_reset_success"

        # estabilizar timestamp para idempotencia
        if not reset_datetime_utc:
            reset_datetime_utc = datetime.now(tz.utc).strftime("%Y-%m-%d %H:%M:%S")

        idempotency_key = self._generate_idempotency_key(email_type, auth_user_id, reset_datetime_utc)

        html, text, used_template = self._build_password_reset_success_body(
            full_name=full_name,
            ip_address=ip_address,
            user_agent=user_agent,
            reset_datetime_utc=reset_datetime_utc,
        )

        logger.info(
            "[MailerSend] password_reset_success: to=%s template=%s",
            (to_email[:3] + "***") if to_email else "unknown",
            "loaded" if used_template else "fallback",
        )

        await self._log_email_event(
            email_type=email_type,
            status="pending",
            to_email=to_email,
            auth_user_id=auth_user_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
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

            await self._log_email_event(
                email_type=email_type,
                status="sent",
                to_email=to_email,
                auth_user_id=auth_user_id,
                provider_message_id=message_id,
                latency_ms=latency_ms,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            err_code = getattr(e, "error_code", "unknown_error")

            await self._log_email_event(
                email_type=email_type,
                status="failed",
                to_email=to_email,
                auth_user_id=auth_user_id,
                latency_ms=latency_ms,
                error_code=str(err_code),
                error_message=str(e)[:500],
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
            raise


__all__ = ["MailerSendEmailSender", "MailerSendError"]

# Fin del archivo backend/app/shared/integrations/mailersend_email_sender.py


