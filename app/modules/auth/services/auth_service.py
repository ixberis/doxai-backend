
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
    """

    def __init__(
        self,
        db: AsyncSession,
        email_sender: Optional[EmailSender] = None,
        recaptcha_verifier: Optional[Any] = None,
        token_issuer: Optional[TokenIssuerService] = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        # IMPORTANTE: usar la API real de EmailSender (from_env), no from_settings
        self.email_sender = email_sender or EmailSender.from_env()
        self.recaptcha_verifier = recaptcha_verifier
        self.token_issuer = token_issuer or TokenIssuerService()

        # Flow services
        self._registration_flow = RegistrationFlowService(
            db=self.db,
            email_sender=self.email_sender,
            token_issuer=self.token_issuer,
        )
        self._activation_flow = ActivationFlowService(
            db=self.db,
            email_sender=self.email_sender,
        )
        self._password_reset_flow = PasswordResetFlowService(
            db=self.db,
            email_sender=self.email_sender,
        )
        self._login_flow = LoginFlowService(
            db=self.db,
            token_issuer=self.token_issuer,
        )

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
        
        await verify_recaptcha_or_raise(
            recaptcha_token,
            self.recaptcha_verifier,
            action="register",
            ip_address=ip_address,
        )
        return await self._registration_flow.register_user(payload)

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
        return await self._activation_flow.resend_activation(data)

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
        
        # Validar CAPTCHA antes de procesar (anti-abuso)
        await verify_recaptcha_or_raise(
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