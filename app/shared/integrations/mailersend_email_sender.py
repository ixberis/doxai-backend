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
        self._db_session = db_session  # Legacy, kept for backwards compatibility
        self._event_session_factory = event_session_factory  # async_sessionmaker for event logging

    # ─────────────────────────────────────────────────────────────────────────
    # Event Logging Helpers (for auth_email_events metrics)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _generate_idempotency_key(email_type: str, auth_user_id: Optional[UUID], unique_context: str) -> str:
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

        Silently fails if no session factory or on error (doesn't block email sending).
        """
        session_factory = self._get_event_session_factory()
        if session_factory is None:
            logger.warning(
                "auth_email_event_insert_skipped: no session_factory type=%s status=%s",
                email_type,
                status,
            )
            return

        logger.info(
            "auth_email_event_insert_started: type=%s status=%s auth_user_id=%s domain=%s",
            email_type,
            status,
            (str(auth_user_id)[:8] + "...") if auth_user_id else None,
            self._extract_domain(to_email),
        )

        try:
            from sqlalchemy import text

            async with session_factory() as log_session:
                q = text("""
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
                """)

                result = await log_session.execute(q, {
                    "email_type": email_type,
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
                })

                row = result.first()
                event_id = row[0] if row else None
                await log_session.commit()

            logger.info(
                "auth_email_event_insert_success: event_id=%s type=%s status=%s latency_ms=%s",
                event_id,
                email_type,
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

    @classmethod
    def from_settings(
        cls,
        settings: "BaseAppSettings",
        db_session: Optional["AsyncSession"] = None,
        event_session_factory: Optional["async_sessionmaker[AsyncSession]"] = None,
    ) -> "MailerSendEmailSender":
        """
        Crea instancia desde settings (fuente de verdad).
        """
        api_key = ""
        if settings.mailersend_api_key:
            api_key = settings.mailersend_api_key.get_secret_value().strip()

        from_email = (settings.mailersend_from_email or "").strip()
        from_name = (settings.mailersend_from_name or "DoxAI").strip()
        timeout = settings.email_timeout_sec or 30
        frontend_url = _normalize_base_url(
            getattr(settings, "frontend_base_url", None) or settings.frontend_url
        )

        if not api_key:
            raise ValueError("[MailerSend] MAILERSEND_API_KEY es requerido. Configúrelo en Railway/Vercel.")
        if not from_email:
            raise ValueError("[MailerSend] MAILERSEND_FROM_EMAIL es requerido. Configúrelo en Railway/Vercel.")

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

    # -------------------------------------------------------------------------
    # (resto del archivo SIN CAMBIOS de lógica, solo ajusté send_* firmas/llamadas)
    # -------------------------------------------------------------------------

    async def send_activation_email(
        self,
        to_email: str,
        full_name: str,
        activation_token: str,
        *,
        auth_user_id: Optional[UUID] = None,
        user_id: Optional[int] = None,  # legacy (no persist)
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
            )
            raise

    async def send_password_reset_email(
        self,
        to_email: str,
        full_name: str,
        reset_token: str,
        *,
        auth_user_id: Optional[UUID] = None,
        user_id: Optional[int] = None,  # legacy (no persist)
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
            )
            raise

    async def send_welcome_email(
        self,
        to_email: str,
        full_name: str,
        credits_assigned: int,
        *,
        auth_user_id: Optional[UUID] = None,
        user_id: Optional[int] = None,  # legacy (no persist)
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
            )
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # El resto del archivo (builders, _send_email, admin notice, reset success)
    # se mantiene como está en tu base; solo necesitarás pasar auth_user_id
    # desde los callsites (RegistrationFlowService / ActivationFlowService).
    # ─────────────────────────────────────────────────────────────────────────

