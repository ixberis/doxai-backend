
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/registration_flow_service.py

Flujo de registro de usuario con anti-enumeración estricta:
- Verifica existencia de usuario (la verificación de reCAPTCHA se hace antes,
  en AuthService.register_user).
- Maneja el caso de usuario ya existente (activo o no) con respuesta genérica
  que NO revela si el email existe en el sistema.
- Crea usuario nuevo si no existe.
- Emite token de activación.
- Envía correo de activación.
- Registra eventos en AuditService.

ANTI-ENUMERACIÓN:
- Email existente (activo o no) → 200 OK + mensaje genérico
- Email nuevo → 201 Created + user_id + access_token
- El mensaje para email existente es idéntico independientemente del estado

Autor: Ixchel Beristain
Actualizado: 20/12/2025
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from fastapi import status
from sqlalchemy import update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models.activation_models import AccountActivation
from app.modules.auth.models.user_models import AppUser
from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.services.audit_service import AuditService
from app.modules.auth.services.token_issuer_service import TokenIssuerService
from app.modules.auth.utils.payload_extractors import as_dict
from app.shared.integrations.email_sender import EmailSender
from app.shared.utils.security import hash_password, PasswordTooLongError, MAX_PASSWORD_LENGTH
from app.shared.utils.http_exceptions import BadRequestException, UnprocessableEntityException

logger = logging.getLogger(__name__)


# Mensaje genérico para anti-enumeración (usado cuando email ya existe)
GENERIC_REGISTER_MESSAGE = (
    "Si el correo es válido, recibirás instrucciones para activar tu cuenta. "
    "Si no llega, revisa Spam o usa 'Reenviar activación'."
)


@dataclass
class RegistrationResult:
    """Resultado interno del registro (no expuesto en API)."""
    payload: Dict[str, Any]
    created: bool


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

    async def register_user(self, data: Mapping[str, Any] | Any) -> RegistrationResult:
        """
        Registra un usuario nuevo o maneja caso de email existente.

        ANTI-ENUMERACIÓN ESTRICTA:
        - Email existente (activo o no) → respuesta genérica sin user_id/access_token
        - Email nuevo → respuesta con user_id y access_token

        data esperado:
            - email
            - password
            - full_name (opcional)
            - ip_address (opcional)
            - user_agent (opcional)

        Returns:
            RegistrationResult con:
                - payload: Dict (message, y opcionalmente user_id/access_token)
                - created: bool (True solo si se creó usuario nuevo)
        """
        payload = as_dict(data)

        email = (payload.get("email") or "").strip().lower()
        password = payload.get("password") or ""
        full_name = (payload.get("full_name") or "").strip() or None
        # Soportar aliases: phone, user_phone, phone_number
        phone = (
            payload.get("phone") 
            or payload.get("user_phone") 
            or payload.get("phone_number") 
            or ""
        ).strip() or None
        ip_address = payload.get("ip_address", "unknown")
        user_agent = payload.get("user_agent")

        # DEBUG: Log payload keys y presencia de phone (sin PII)
        logger.info(
            "REGISTRATION_PAYLOAD: payload_keys=%s has_phone=%s phone_len=%d email_prefix=%s",
            list(payload.keys()),
            bool(phone),
            len(phone) if phone else 0,
            email[:3] + "***" if email else "empty",
        )

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
        # 1) Usuario ya existe (ANTI-ENUMERACIÓN: mismo tratamiento activo/inactivo)
        # ------------------------------------------------------------------
        existing = await self.user_service.get_by_email(email)
        if existing:
            is_active = await self.activation_service.is_active(existing)
            
            if is_active:
                # Usuario activo: log como intento duplicado, respuesta genérica
                logger.info(
                    "register_duplicate_active email=%s ip=%s",
                    email[:3] + "***",
                    ip_address,
                )
                self.audit_service.log_register_failed(
                    email=email,
                    ip_address=ip_address,
                    error_message="email_already_registered_active",
                    user_agent=user_agent,
                    extra_data={"user_id": str(existing.user_id)},
                )
            else:
                # Usuario no activo: reenviar activación best-effort
                token = await self.activation_service.issue_activation_token(
                    user_id=existing.user_id,
                )
                await self._send_activation_email_best_effort(
                    email=existing.user_email,
                    full_name=existing.user_full_name,
                    token=token,
                    user_id=existing.user_id,
                    ip_address=ip_address,
                )
                logger.info(
                    "register_duplicate_inactive email=%s ip=%s",
                    email[:3] + "***",
                    ip_address,
                )

            # ANTI-ENUMERACIÓN: misma respuesta para activo e inactivo
            # NO incluye user_id ni access_token
            return RegistrationResult(
                payload={"message": GENERIC_REGISTER_MESSAGE},
                created=False,
            )

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
            user_phone=phone,  # Persistir teléfono del registro
        )

        # DEBUG logging (no PII) - confirma que teléfono se recibe
        logger.info(
            "REGISTRATION: crear usuario nuevo email=%s has_phone=%s phone_len=%d",
            email[:3] + "***",
            bool(phone),
            len(phone) if phone else 0,
        )
        try:
            created = await self.user_service.add(user)
        except IntegrityError as e:
            # Race condition: email insertado entre get_by_email y add
            # ANTI-ENUMERACIÓN: respuesta genérica (no 409)
            logger.warning(
                "register_integrity_error email=%s ip=%s error=%s",
                email[:3] + "***",
                ip_address,
                str(e)[:100],
            )
            self.audit_service.log_register_failed(
                email=email,
                ip_address=ip_address,
                error_message="integrity_error_race_condition",
                user_agent=user_agent,
            )
            return RegistrationResult(
                payload={"message": GENERIC_REGISTER_MESSAGE},
                created=False,
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

        return RegistrationResult(
            payload={
                "user_id": created.user_id,
                "access_token": access_token,
                "message": message,
                "activation_email_sent": email_sent,
            },
            created=True,
        )


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
        Envía email de activación de forma best-effort y persiste tracking en DB.
        
        No propaga excepciones. Loguea resultado.
        Actualiza activation_email_status/attempts/sent_at/last_error en account_activations.
        
        IMPORTANTE: Usa commit() explícito porque create_activation ya hizo commit previo.
        El flush() solo sincroniza sin persistir, causando pérdida de datos.
        
        Usa WHERE user_id + token para máxima seguridad (aunque token es UNIQUE).
        Usa func.coalesce para el incremento de attempts (robusto ante NULL).
        
        Returns:
            True si se envió correctamente, False si falló.
        """
        email_masked = email[:3] + "***" if email else "unknown"
        token_preview = token[:12] + "..." if token else "none"
        now_utc = datetime.now(timezone.utc)
        
        try:
            await self.email_sender.send_activation_email(
                to_email=email,
                full_name=full_name or "",
                activation_token=token,
            )
            
            # Persistir éxito: status='sent', attempts++, sent_at=now, last_error=null
            # WHERE solo por token (es UNIQUE, suficiente para identificar)
            result = await self.db.execute(
                update(AccountActivation)
                .where(AccountActivation.token == token)
                .values(
                    activation_email_status='sent',
                    activation_email_attempts=func.coalesce(
                        AccountActivation.activation_email_attempts, 0
                    ) + 1,
                    activation_email_sent_at=now_utc,
                    activation_email_last_error=None,
                )
            )
            
            try:
                await self.db.commit()
            except Exception as commit_error:
                await self.db.rollback()
                logger.error(
                    "activation_email_tracking_commit_failed user_id=%s token_preview=%s error=%s",
                    user_id,
                    token_preview,
                    str(commit_error)[:100],
                )
                # Email se envió OK, pero tracking falló - aún retornamos True
                logger.info(
                    "activation_email_sent to=%s user_id=%s ip=%s (tracking_failed)",
                    email_masked,
                    user_id,
                    ip_address,
                )
                return True
            
            # Verificar rowcount
            if result.rowcount != 1:
                logger.warning(
                    "activation_email_tracking_update_missed user_id=%s token_preview=%s rowcount=%s expected=1",
                    user_id,
                    token_preview,
                    result.rowcount,
                )
            else:
                logger.info(
                    "activation_email_tracking_persisted user_id=%s status=sent",
                    user_id,
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
            error_msg = f"{error_code}: {str(e)[:180]}"
            
            # Persistir fallo: status='failed', attempts++, last_error
            # WHERE solo por token (es UNIQUE, suficiente para identificar)
            try:
                result = await self.db.execute(
                    update(AccountActivation)
                    .where(AccountActivation.token == token)
                    .values(
                        activation_email_status='failed',
                        activation_email_attempts=func.coalesce(
                            AccountActivation.activation_email_attempts, 0
                        ) + 1,
                        activation_email_last_error=error_msg,
                    )
                )
                await self.db.commit()
                
                if result.rowcount != 1:
                    logger.warning(
                        "activation_email_tracking_update_missed user_id=%s token_preview=%s rowcount=%s expected=1",
                        user_id,
                        token_preview,
                        result.rowcount,
                    )
            except Exception as commit_error:
                await self.db.rollback()
                logger.error(
                    "activation_email_tracking_commit_failed user_id=%s token_preview=%s error=%s",
                    user_id,
                    token_preview,
                    str(commit_error)[:100],
                )
            
            logger.warning(
                "activation_email_failed to=%s user_id=%s ip=%s error_code=%s error=%s",
                email_masked,
                user_id,
                ip_address,
                error_code,
                str(e)[:200],
            )
            return False


__all__ = ["RegistrationFlowService", "RegistrationResult", "GENERIC_REGISTER_MESSAGE"]

# Fin del script backend/app/modules/auth/services/registration_flow_service.py