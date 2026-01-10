# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/auth_service.py

Servicio orquestador de alto nivel del módulo Auth.
Expone los casos de uso:
- register_user / register
- activate_account / activate
- resend_activation_email
- start_password_reset / start_reset
- confirm_password_reset / confirm_reset
- login
- refresh_tokens

La lógica de negocio detallada se delega a los "flow services":
- RegistrationFlowService
- ActivationFlowService
- PasswordResetFlowService
- LoginFlowService

Autor: Ixchel Beristain
Actualizado: 19/11/2025
Actualizado: 2026-01-09
  - Lazy-loading de EmailSender para evitar overhead (MailerSend) en login.
  - Lazy-loading de flow services que dependen de EmailSender.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.services.registration_flow_service import RegistrationFlowService
from app.modules.auth.services.activation_flow_service import ActivationFlowService
from app.modules.auth.services.password_reset_flow_service import PasswordResetFlowService
from app.modules.auth.services.login_flow_service import LoginFlowService
from app.modules.auth.utils.payload_extractors import as_dict
from app.modules.auth.utils.recaptcha_helpers import verify_recaptcha_or_raise
from app.modules.auth.services.token_issuer_service import TokenIssuerService
from app.shared.integrations.email_sender import EmailSender
from app.shared.config.config_loader import get_settings


class AuthService:
    """
    Orquestador principal del módulo Auth.

    Nota:
        Mantiene compatibilidad con la interfaz anterior de AuthService,
        pero internamente delega la lógica a servicios de flujo más pequeños.

    Performance:
        Login NO usa email. Inicializar EmailSender (MailerSend) puede costar segundos.
        Por eso, EmailSender y los flows que dependen de él se inicializan LAZY.
    """

    def __init__(
        self,
        db: AsyncSession,
        email_sender: Optional[EmailSender] = None,
        recaptcha_verifier: Optional[Any] = None,
        token_issuer: Optional[TokenIssuerService] = None,
        verify_recaptcha_fn: Optional[Any] = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()

        # reCAPTCHA / tokens
        self.recaptcha_verifier = recaptcha_verifier
        self.token_issuer = token_issuer or TokenIssuerService()
        self._verify_recaptcha = (
            verify_recaptcha_fn if verify_recaptcha_fn is not None else verify_recaptcha_or_raise
        )

        # ──────────────────────────────────────────────────────────────────
        # Lazy dependencies
        # ──────────────────────────────────────────────────────────────────
        self._email_sender_instance: Optional[EmailSender] = email_sender
        self._email_sender_initialized: bool = email_sender is not None

        self._registration_flow_instance: Optional[RegistrationFlowService] = None
        self._activation_flow_instance: Optional[ActivationFlowService] = None
        self._password_reset_flow_instance: Optional[PasswordResetFlowService] = None
        self._login_flow_instance: Optional[LoginFlowService] = None

    # ──────────────────────────────────────────────────────────────────────
    # Lazy properties
    # ──────────────────────────────────────────────────────────────────────

    @property
    def email_sender(self) -> EmailSender:
        """
        Lazy-load EmailSender solo cuando se necesita (registro/activación/reset).
        Login NO lo usa, así que evitamos overhead en /auth/login.
        """
        if not self._email_sender_initialized:
            # IMPORTANTE: pasar db_session para instrumentación de auth_email_events
            self._email_sender_instance = EmailSender.from_env(db_session=self.db)
            self._email_sender_initialized = True
        # mypy: ya está inicializado aquí
        return self._email_sender_instance  # type: ignore[return-value]

    @property
    def _registration_flow(self) -> RegistrationFlowService:
        if self._registration_flow_instance is None:
            self._registration_flow_instance = RegistrationFlowService(
                db=self.db,
                email_sender=self.email_sender,
                token_issuer=self.token_issuer,
            )
        return self._registration_flow_instance

    @property
    def _activation_flow(self) -> ActivationFlowService:
        if self._activation_flow_instance is None:
            self._activation_flow_instance = ActivationFlowService(
                db=self.db,
                email_sender=self.email_sender,
            )
        return self._activation_flow_instance

    @property
    def _password_reset_flow(self) -> PasswordResetFlowService:
        if self._password_reset_flow_instance is None:
            self._password_reset_flow_instance = PasswordResetFlowService(
                db=self.db,
                email_sender=self.email_sender,
            )
        return self._password_reset_flow_instance

    @property
    def _login_flow(self) -> LoginFlowService:
        """
        LoginFlow NO usa EmailSender. Inicialización directa para evitar overhead.
        """
        if self._login_flow_instance is None:
            self._login_flow_instance = LoginFlowService(
                db=self.db,
                token_issuer=self.token_issuer,
            )
        return self._login_flow_instance

    # ------------------------------------------------------------------ #
    # Registro
    # ------------------------------------------------------------------ #
    async def register_user(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Registra un usuario. Verifica reCAPTCHA (si está habilitado) y
        delega el resto del flujo a RegistrationFlowService.
        """
        payload = as_dict(data)
        recaptcha_token = payload.get("recaptcha_token")
        ip_address = payload.get("ip_address", "unknown")

        await self._verify_recaptcha(
            recaptcha_token,
            self.recaptcha_verifier,
            action="register",
            ip_address=ip_address,
        )
        result = await self._registration_flow.register_user(payload)
        return result.payload

    async def register(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """Alias para mantener compatibilidad."""
        return await self.register_user(data)

    # ------------------------------------------------------------------ #
    # Activación
    # ------------------------------------------------------------------ #
    async def activate_account(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        return await self._activation_flow.activate_account(data)

    async def activate(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        return await self.activate_account(data)

    async def resend_activation_email(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Reenvía correo de activación.
        Verifica reCAPTCHA (si está habilitado) ANTES de ejecutar el flujo.
        """
        payload = as_dict(data)
        recaptcha_token = payload.get("recaptcha_token")
        ip_address = payload.get("ip_address", "unknown")

        await self._verify_recaptcha(
            recaptcha_token,
            self.recaptcha_verifier,
            action="activation_resend",
            ip_address=ip_address,
        )

        return await self._activation_flow.resend_activation(payload)

    # ------------------------------------------------------------------ #
    # Restablecimiento de contraseña
    # ------------------------------------------------------------------ #
    async def start_password_reset(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Inicia el flujo de restablecimiento de contraseña.
        Verifica reCAPTCHA (si está habilitado) ANTES de ejecutar el flujo.
        """
        payload = as_dict(data)
        recaptcha_token = payload.get("recaptcha_token")
        ip_address = payload.get("ip_address", "unknown")

        await self._verify_recaptcha(
            recaptcha_token,
            self.recaptcha_verifier,
            action="password_forgot",
            ip_address=ip_address,
        )

        return await self._password_reset_flow.start_password_reset(payload)

    async def start_reset(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        return await self.start_password_reset(data)

    async def confirm_password_reset(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        return await self._password_reset_flow.confirm_password_reset(data)

    async def confirm_reset(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        return await self.confirm_password_reset(data)

    # ------------------------------------------------------------------ #
    # Login y refresh de tokens
    # ------------------------------------------------------------------ #
    async def login(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        payload = as_dict(data)
        return await self._login_flow.login(payload)

    async def refresh_tokens(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        return await self._login_flow.refresh_tokens(data)


__all__ = ["AuthService"]

# Fin del script backend/app/modules/auth/services/auth_service.py
