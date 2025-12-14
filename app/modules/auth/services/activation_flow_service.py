
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/activation_flow_service.py

Flujo de activación de cuenta y reenvío de correos de activación.
Coordinación entre ActivationService, UserService, CreditService,
EmailSender y AuditService.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.audit_service import AuditService
from app.modules.auth.utils.payload_extractors import as_dict
from app.modules.auth.utils.email_helpers import (
    send_activation_email_or_raise,
    send_welcome_email_safely,
)
from app.shared.integrations.email_sender import EmailSender
from app.shared.config.config_loader import get_settings

logger = logging.getLogger(__name__)


class ActivationFlowService:
    """Orquestador del flujo de activación y reenvío de activación."""

    # Rate limiter compartido entre instancias (class-level)
    _resend_timestamps: dict = {}
    _RESEND_COOLDOWN_SECONDS: int = 60

    def __init__(
        self,
        db: AsyncSession,
        email_sender: EmailSender,
    ) -> None:
        self.db = db
        self.email_sender = email_sender
        self.settings = get_settings()
        self.activation_service = ActivationService(db)
        self.user_service = UserService.with_session(db)

    async def activate_account(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Activa la cuenta con base en el token recibido.

        data esperado:
            - token
            - email (opcional, usado para localizar usuario y enviar bienvenida)
        """
        payload = as_dict(data)
        token = payload.get("token")
        email_hint = (payload.get("email") or "").strip().lower()

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de activación requerido.",
            )

        # 1) delegar activación al ActivationService
        result = await self.activation_service.activate_account(token)
        code = result.get("code")
        warnings = result.get("warnings", [])

        # 2) si se activó la cuenta, enviar correo de bienvenida (opcional)
        if code == "ACCOUNT_ACTIVATED" and email_hint:
            user = await self.user_service.get_by_email(email_hint)
            if user:
                # correo de bienvenida (no interrumpe el flujo si falla)
                await send_welcome_email_safely(
                    self.email_sender,
                    email=user.user_email,
                    full_name=user.user_full_name,
                    credits_assigned=result.get("credits_assigned", 0),
                )

                try:
                    AuditService.log_activation_success(
                        user_id=str(user.user_id),
                        email=user.user_email,
                    )
                except Exception as e:
                    logger.warning(f"Audit log_activation_success failed: {e}")

        response = {
            "message": result.get("message", ""),
            "code": code,
            "credits_assigned": result.get("credits_assigned", 0),
        }
        
        # Propagar warnings si existen
        if warnings:
            response["warnings"] = warnings
        
        return response

    async def resend_activation(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Reenvía correo de activación si el usuario existe y no está activo.
        Incluye rate limiting básico (1 request/minuto por email).

        data esperado:
            - email
        """
        import time
        
        payload = as_dict(data)
        email = (payload.get("email") or "").strip().lower()

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email requerido.",
            )

        # Rate limiting básico (in-memory)
        now = time.time()
        last_request = self._resend_timestamps.get(email, 0)
        if now - last_request < self._RESEND_COOLDOWN_SECONDS:
            logger.warning(f"Resend activation rate limited for email={email[:3]}***")
            # Siempre responder 200 para no filtrar info
            return {"message": "Si su cuenta existe, reenviaremos el correo de activación."}
        
        self._resend_timestamps[email] = now

        user = await self.user_service.get_by_email(email)
        if not user:
            # No revelamos existencia
            logger.info(f"Resend activation: email not found (not revealing)")
            return {"message": "Si su cuenta existe, reenviaremos el correo de activación."}

        if await self.activation_service.is_active(user):
            return {"message": "La cuenta ya se encuentra activa."}

        token = await self.activation_service.issue_activation_token(
            user_id=str(user.user_id),
        )

        await send_activation_email_or_raise(
            self.email_sender,
            email=user.user_email,
            full_name=user.user_full_name,
            token=token,
        )

        try:
            AuditService.log_activation_resend(
                user_id=str(user.user_id),
                email=user.user_email,
            )
        except Exception as e:
            logger.warning(f"Audit log_activation_resend failed: {e}")

        return {"message": "Correo de activación reenviado. Revise su bandeja de entrada."}


__all__ = ["ActivationFlowService"]

# Fin del script backend/app/modules/auth/services/activation_flow_service.py
