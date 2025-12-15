
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
from app.modules.auth.repositories import UserRepository
from app.modules.auth.utils.payload_extractors import as_dict
from app.modules.auth.utils.email_helpers import (
    send_activation_email_or_raise,
    send_welcome_email_safely,
)
from app.modules.auth.utils.error_classifier import classify_email_error
from app.modules.auth.metrics.collectors.welcome_email_collectors import (
    welcome_email_sent_total,
    welcome_email_failed_total,
    welcome_email_claimed_total,
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
        self.user_repo = UserRepository(db)  # Para operación atómica anti-race

    async def activate_account(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Activa la cuenta con base en el token recibido.
        Envía correo de bienvenida (idempotente, anti-race condition).

        data esperado:
            - token

        Flujo de idempotencia (estado explícito + claim atómico):
            1. Intentar claim atómico: UPDATE ... SET status='pending' WHERE status IS NULL
            2. Solo si rowcount == 1 (ganamos la carrera) -> enviar correo
            3. En éxito -> status='sent', sent_at=now()
            4. En error -> status='failed', last_error=str(e)
            5. Si rowcount == 0 -> ya claimed/sent/failed (skip)
        """
        payload = as_dict(data)
        token = payload.get("token")

        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de activación requerido.",
            )

        # 1) Delegar activación al ActivationService (obtiene user_id del token)
        result = await self.activation_service.activate_account(token)
        code = result.get("code")
        warnings = result.get("warnings", [])
        activated_user_id = result.get("user_id")

        # 2) Enviar correo de bienvenida (solo si activación exitosa)
        #    Condiciones para envío:
        #    - code == ACCOUNT_ACTIVATED (no ALREADY_ACTIVATED, TOKEN_INVALID, etc.)
        #    - user_id presente
        if code == "ACCOUNT_ACTIVATED" and activated_user_id:
            user = await self.user_service.get_by_id(activated_user_id)
            if user:
                await self._send_welcome_email_with_claim(
                    user=user,
                    credits_assigned=result.get("credits_assigned", 0),
                )

                # Log de auditoría (siempre, independiente del correo)
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

    async def _send_welcome_email_with_claim(
        self,
        user,
        credits_assigned: int,
    ) -> None:
        """
        Envía correo de bienvenida con claim atómico anti-race.
        
        Flujo:
            1. claim_welcome_email_if_pending() - claim atómico (con reclaim de stale)
            2. Si ganamos la carrera -> enviar correo
            3. mark_welcome_email_sent() o mark_welcome_email_failed()
            4. commit transacción (o rollback en error)
        """
        user_id = int(user.user_id)
        email_masked = user.user_email[:3] + "***"

        # Claim atómico: solo 1 proceso gana la carrera (con reclaim de stale pending)
        claimed, attempts = await self.user_repo.claim_welcome_email_if_pending(user_id)

        if not claimed:
            # Ya estaba claimed/sent/failed (otro request ganó o ya se procesó)
            logger.info(
                "welcome_email_skipped_already_claimed user_id=%s email=%s",
                user_id,
                email_masked,
            )
            return

        # Ganamos la carrera -> somos responsables de enviar
        # Métrica: claim exitoso
        welcome_email_claimed_total.inc()
        
        logger.info(
            "welcome_email_claimed user_id=%s email=%s attempt=%d",
            user_id,
            email_masked,
            attempts,
        )

        try:
            await send_welcome_email_safely(
                self.email_sender,
                email=user.user_email,
                full_name=user.user_full_name,
                credits_assigned=credits_assigned,
            )

            # Éxito: marcar como enviado
            await self.user_repo.mark_welcome_email_sent(user_id)
            await self.db.commit()

            # Métrica: envío exitoso
            welcome_email_sent_total.labels(provider="smtp").inc()

            logger.info(
                "welcome_email_sent user_id=%s email=%s credits=%d attempt=%d",
                user_id,
                email_masked,
                credits_assigned,
                attempts,
            )

        except Exception as e:
            # Rollback explícito para no dejar sesión sucia
            await self.db.rollback()
            
            # Fallo: marcar como failed con error (nueva transacción)
            error_msg = str(e)[:500]
            reason = classify_email_error(e)
            
            try:
                await self.user_repo.mark_welcome_email_failed(user_id, error_msg)
                await self.db.commit()
            except Exception as mark_error:
                logger.error(
                    "welcome_email_mark_failed_error user_id=%s error=%s",
                    user_id,
                    mark_error,
                )
                await self.db.rollback()

            # Métrica: fallo
            welcome_email_failed_total.labels(provider="smtp", reason=reason).inc()

            logger.error(
                "welcome_email_failed user_id=%s email=%s error=%s attempt=%d",
                user_id,
                email_masked,
                error_msg,
                attempts,
            )

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
