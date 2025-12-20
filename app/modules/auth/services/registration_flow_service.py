
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/registration_flow_service.py

Flujo de registro de usuario:
- Verifica existencia de usuario (la verificación de reCAPTCHA se hace antes,
  en AuthService.register_user).
- Maneja el caso de usuario ya existente:
    - Si está activo: 409
    - Si no está activo: reenvía activación y devuelve access_token + mensaje.
- Crea usuario nuevo si no existe.
- Emite token de activación.
- Envía correo de activación.
- Registra eventos en AuditService.

Devuelve fields compatibles con RegisterResponse:
    - message: str
    - user_id: int
    - access_token: str

Autor: Ixchel Beristain
Actualizado: 20/11/2025
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models.user_models import AppUser
from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.services.audit_service import AuditService
from app.modules.auth.services.token_issuer_service import TokenIssuerService
from app.modules.auth.utils.payload_extractors import as_dict
from app.shared.integrations.email_sender import EmailSender
from app.shared.utils.security import hash_password, PasswordTooLongError, MAX_PASSWORD_LENGTH
from app.shared.utils.http_exceptions import BadRequestException, ConflictException, UnprocessableEntityException

logger = logging.getLogger(__name__)


class RegistrationFlowService:
    """Orquestador del flujo de registro de usuarios."""

    def __init__(
        self,
        db: AsyncSession,
        email_sender: EmailSender,
        token_issuer: TokenIssuerService,
        user_service: Optional[UserService] = None,
        activation_service: Optional[ActivationService] = None,
        audit_service: Optional[AuditService] = None,
    ) -> None:
        """
        Constructor flexible para integrarse con AuthService.

        AuthService hoy solo pasa:
            db, email_sender, token_issuer

        Por eso aquí:
            - Si no se recibe user_service, se crea con `db`.
            - Si no se recibe activation_service, se crea con `db`.
            - Si no se recibe audit_service, se usa la clase AuditService como singleton.
        """
        self.db = db
        self.email_sender = email_sender
        self.token_issuer = token_issuer

        # Servicios dependientes (con defaults razonables)
        self.user_service = user_service or UserService.with_session(db)
        self.activation_service = activation_service or ActivationService(db)
        # AuditService es básicamente estático; usamos la clase directamente si no se inyecta otra cosa
        self.audit_service = audit_service or AuditService

    async def register_user(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Registra un usuario nuevo o reenvía activación si ya existe.

        data esperado:
            - email
            - password
            - full_name (opcional)
            - ip_address (opcional)
            - user_agent (opcional)
            - recaptcha_token ya debió haberse validado en AuthService.

        Returns:
            Dict con:
                - message: str
                - user_id: int
                - access_token: str
        """
        payload = as_dict(data)

        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        full_name = (payload.get("full_name") or "").strip() or None
        ip_address = payload.get("ip_address", "unknown")
        user_agent = payload.get("user_agent")

        if not email or not password:
            self.audit_service.log_register_failed(
                email=email or "<empty>",
                ip_address=ip_address,
                error_message="missing_email_or_password",
                user_agent=user_agent,
            )
            raise BadRequestException(
                detail="Email y contraseña son obligatorios.",
            )

        # ------------------------------------------------------------------
        # 1) Usuario ya existe
        # ------------------------------------------------------------------
        existing = await self.user_service.get_by_email(email)
        if existing:
            # Si ya está activo -> 409
            if await self.activation_service.is_active(existing):
                self.audit_service.log_register_failed(
                    email=email,
                    ip_address=ip_address,
                    error_message="email_already_registered",
                    user_agent=user_agent,
                    extra_data={"user_id": str(existing.user_id)},
                )
                raise ConflictException(
                    detail="No se pudo completar el registro. Si ya tiene una cuenta, inicie sesión o recupere su contraseña.",
                    error_code="email_already_registered",
                )

            # Usuario existe pero NO está activo: reenviar activación
            token = await self.activation_service.issue_activation_token(
                user_id=existing.user_id,
            )
            
            # Best-effort: intentar enviar email, pero no fallar el registro
            email_sent = await self._send_activation_email_best_effort(
                email=existing.user_email,
                full_name=existing.user_full_name,
                token=token,
                user_id=existing.user_id,
                ip_address=ip_address,
            )

            access_token = self.token_issuer.create_access_token(
                sub=str(existing.user_id),
            )

            self.audit_service.log_register_success(
                user_id=str(existing.user_id),
                email=existing.user_email,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Mensaje depende de si se envió el email
            message = (
                "Correo de activación reenviado. Revise su bandeja de entrada."
                if email_sent
                else "Cuenta creada. Si no recibes el correo de activación, usa 'Reenviar activación' en inicio de sesión."
            )

            return {
                "user_id": existing.user_id,
                "access_token": access_token,
                "message": message,
            }

        # ------------------------------------------------------------------
        # 2) Usuario nuevo
        # ------------------------------------------------------------------
        try:
            password_hash = hash_password(password)
        except PasswordTooLongError:
            self.audit_service.log_register_failed(
                email=email,
                ip_address=ip_address,
                error_message="password_too_long",
                user_agent=user_agent,
            )
            raise UnprocessableEntityException(
                detail=f"La contraseña es demasiado larga (máximo {MAX_PASSWORD_LENGTH} caracteres)."
            )

        user = AppUser(
            user_email=email,
            user_full_name=full_name or "",
            user_password_hash=password_hash,
        )

        logger.info("REGISTRATION: crear usuario nuevo %s", email)
        try:
            created = await self.user_service.add(user)
        except IntegrityError as e:
            logger.error("Error de integridad al registrar usuario %s: %s", email, e)
            self.audit_service.log_register_failed(
                email=email,
                ip_address=ip_address,
                error_message="integrity_error_email_in_use",
                user_agent=user_agent,
            )
            raise ConflictException(
                detail="No se pudo completar el registro. Si ya tiene una cuenta, inicie sesión o recupere su contraseña.",
                error_code="email_already_registered",
            )

        logger.info("REGISTRATION: crear token de activación y enviar correo")
        token = await self.activation_service.issue_activation_token(
            user_id=created.user_id,
        )
        
        # Best-effort: intentar enviar email, pero no fallar el registro
        email_sent = await self._send_activation_email_best_effort(
            email=created.user_email,
            full_name=created.user_full_name,
            token=token,
            user_id=created.user_id,
            ip_address=ip_address,
        )

        access_token = self.token_issuer.create_access_token(
            sub=str(created.user_id),
        )

        self.audit_service.log_register_success(
            user_id=str(created.user_id),
            email=created.user_email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Mensaje depende de si se envió el email
        message = (
            "Usuario registrado. Revise su correo para activar la cuenta."
            if email_sent
            else "Cuenta creada. Si no recibes el correo de activación, usa 'Reenviar activación' en inicio de sesión."
        )

        return {
            "user_id": created.user_id,
            "access_token": access_token,
            "message": message,
        }


    async def _send_activation_email_best_effort(
        self,
        *,
        email: str,
        full_name: str,
        token: str,
        user_id: int,
        ip_address: str,
    ) -> bool:
        """
        Envía email de activación de forma best-effort.
        
        No propaga excepciones. Loguea resultado.
        
        Returns:
            True si se envió correctamente, False si falló.
        """
        email_masked = email[:3] + "***" if email else "unknown"
        
        try:
            await self.email_sender.send_activation_email(
                to_email=email,
                full_name=full_name or "",
                activation_token=token,
            )
            
            logger.info(
                "activation_email_sent to=%s user_id=%s ip=%s",
                email_masked,
                user_id,
                ip_address,
            )
            return True
            
        except Exception as e:
            # Extraer error_code si es MailerSendError
            error_code = getattr(e, "error_code", "unknown")
            
            logger.warning(
                "activation_email_failed to=%s user_id=%s ip=%s error_code=%s error=%s",
                email_masked,
                user_id,
                ip_address,
                error_code,
                str(e)[:200],
            )
            return False


__all__ = ["RegistrationFlowService"]

# Fin del script backend/app/modules/auth/services/registration_flow_service.py