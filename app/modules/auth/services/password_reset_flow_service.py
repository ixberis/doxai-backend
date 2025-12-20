
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/password_reset_flow_service.py

Flujo completo de restablecimiento de contraseña:
- Inicio de reset (start_password_reset)
- Confirmación de reset (confirm_password_reset)

Orquesta:
- PasswordResetService (tokens + correo + persistencia)
- UserService (para localizar usuario)
- AuditService (registro de eventos de auditoría)

Autor: Ixchel Beristain
Actualizado: 20/11/2025
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.services.password_reset_service import PasswordResetService
from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.audit_service import AuditService
from app.modules.auth.utils.payload_extractors import as_dict
from app.shared.integrations.email_sender import EmailSender
from app.shared.utils.security import hash_password, PasswordTooLongError, MAX_PASSWORD_LENGTH


class PasswordResetFlowService:
    """Orquestador de inicio y confirmación de restablecimiento de contraseña."""

    def __init__(
        self,
        db: AsyncSession,
        email_sender: EmailSender,
    ) -> None:
        self.db = db
        self.email_sender = email_sender
        self.user_service = UserService.with_session(db)
        # PasswordResetService ya se encarga de tokens + persistencia + correo
        self.reset_service = PasswordResetService(db, email_sender=self.email_sender)

    async def start_password_reset(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Inicia el proceso de restablecimiento.

        data esperado:
            - email
            - ip_address (inyectado desde request meta, NO del body)
            - user_agent (inyectado desde request meta, NO del body)
            - recaptcha_token (validado previamente por AuthService)
        
        IMPORTANTE: ip_address y user_agent SOLO deben provenir de get_request_meta(request)
        en el endpoint. No se confía en valores enviados desde el cliente.
        """
        payload = as_dict(data)
        email = (payload.get("email") or "").strip().lower()
        
        # SEGURIDAD: ip_address y user_agent SOLO provienen de request meta
        ip = payload.get("ip_address") or "unknown"
        ua = payload.get("user_agent") or ""

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email requerido.",
            )

        # Recuperamos usuario (si existe), pero NO revelamos su existencia hacia afuera
        # PasswordResetService.start_password_reset se encarga del correo + persistencia.
        result = await self.reset_service.start_password_reset(email)

        # Auditoría: registramos solicitud de reset (no revela existencia real de la cuenta)
        AuditService.log_password_reset_request(
            email=email,
            ip_address=ip,
        )

        return {
            "message": result.get(
                "message",
                "Si el correo está registrado, se enviaron instrucciones.",
            )
        }

    async def confirm_password_reset(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Confirma el restablecimiento usando el token.

        data esperado:
            - token
            - new_password
            - ip_address (inyectado desde request meta, NO del body)
            - user_agent (inyectado desde request meta, NO del body)
        
        IMPORTANTE: ip_address y user_agent SOLO deben provenir de get_request_meta(request)
        en el endpoint. No se confía en valores enviados desde el cliente.
        """
        payload = as_dict(data)
        token = payload.get("token")
        new_password = payload.get("new_password")
        
        # SEGURIDAD: ip_address y user_agent SOLO provienen de request meta (inyectado en endpoint)
        # Estos valores son confiables porque get_request_meta() los extrae del request real
        ip_address = payload.get("ip_address") or "unknown"
        user_agent = payload.get("user_agent") or ""

        if not token or not new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token y nueva contraseña son obligatorios.",
            )

        # Hasheamos la nueva contraseña y delegamos a PasswordResetService
        try:
            new_password_hash = hash_password(new_password)
        except PasswordTooLongError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"La contraseña es demasiado larga (máximo {MAX_PASSWORD_LENGTH} caracteres).",
            )

        result = await self.reset_service.confirm_password_reset(
            token=token,
            new_password_hash=new_password_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if result.get("code") == "TOKEN_INVALID":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Token inválido o expirado."),
            )

        # Aquí podríamos agregar AuditService.log_password_reset_confirm()
        # cuando tengamos user_id/email disponibles desde el token de reset.

        return {
            "message": result.get(
                "message",
                "La contraseña se actualizó correctamente.",
            )
        }


__all__ = ["PasswordResetFlowService"]

# Fin del script backend/app/modules/auth/services/password_reset_flow_service.py