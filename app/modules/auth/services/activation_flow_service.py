
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
from typing import Any, Dict, Mapping, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.services.user_service import UserService
from app.modules.auth.services.audit_service import AuditService
from app.modules.auth.services.welcome_email_service import WelcomeEmailService, IWelcomeEmailService
from app.modules.auth.repositories import UserRepository
from app.modules.auth.utils.payload_extractors import as_dict
from app.modules.auth.utils.email_helpers import (
    send_activation_email_safely,
)
from app.shared.services.admin_notifications import send_admin_activation_notice
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

    def __init__(
        self,
        db: AsyncSession,
        email_sender: EmailSender,
        welcome_email_service: IWelcomeEmailService | None = None,
        audit_service: type | None = None,
    ) -> None:
        self.db = db
        self.email_sender = email_sender
        self.settings = get_settings()
        self.activation_service = ActivationService(db)
        self.user_service = UserService.with_session(db)
        self.user_repo = UserRepository(db)
        self.welcome_email_service: IWelcomeEmailService = (
            welcome_email_service if welcome_email_service is not None
            else WelcomeEmailService(email_sender)
        )
        # Inyección de AuditService (con default si no se provee)
        self.audit_service = audit_service if audit_service is not None else AuditService

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
        token = payload.get("token", "").strip() if payload.get("token") else ""

        # Validación 1: token faltante o vacío
        if not token:
            logger.warning(
                "activation_validation_failed error_code=activation_token_missing ip=%s",
                payload.get("ip_address", "unknown"),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "No se proporcionó un token de activación.",
                    "error_code": "activation_token_missing",
                },
            )

        # Validación 2: token con formato inválido (muy corto)
        if len(token) < 10:
            logger.warning(
                "activation_validation_failed error_code=activation_token_invalid token_length=%d ip=%s",
                len(token),
                payload.get("ip_address", "unknown"),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "El enlace de activación no es válido.",
                    "error_code": "activation_token_invalid",
                },
            )

        # Log de inicio del flujo (token truncado por seguridad)
        token_preview = token[:8] + "..." if len(token) > 8 else token[:4] + "..."
        logger.info(
            "activation_flow_started token_preview=%s ip=%s",
            token_preview,
            payload.get("ip_address", "unknown"),
        )

        # 1) Delegar activación al ActivationService (obtiene user_id del token)
        result = await self.activation_service.activate_account(token)
        code = result.get("code")
        warnings = result.get("warnings", [])
        activated_user_id = result.get("user_id")

        # Manejar errores del servicio de activación
        if code == "TOKEN_INVALID":
            logger.warning(
                "activation_validation_failed error_code=activation_token_invalid reason=not_found ip=%s",
                payload.get("ip_address", "unknown"),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "El enlace de activación no es válido o ya fue utilizado.",
                    "error_code": "activation_token_invalid",
                },
            )

        if code == "TOKEN_EXPIRED":
            logger.warning(
                "activation_validation_failed error_code=activation_token_expired ip=%s",
                payload.get("ip_address", "unknown"),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "El enlace de activación ha expirado. Solicite uno nuevo.",
                    "error_code": "activation_token_expired",
                },
            )

        # 2) Enviar correo de bienvenida (solo si activación exitosa)
        #    Condiciones para envío:
        #    - code == ACCOUNT_ACTIVATED (no ALREADY_ACTIVATED, TOKEN_INVALID, etc.)
        #    - user_id presente
        if code == "ACCOUNT_ACTIVATED" and activated_user_id:
            credits_assigned = result.get("credits_assigned", 0)
            
            # Log de activación exitosa (SIEMPRE)
            logger.info(
                "activation_success user_id=%s credits=%d",
                activated_user_id,
                credits_assigned,
            )
            
            user = await self.user_service.get_by_id(activated_user_id)
            if user:
                await self._send_welcome_email_with_claim(
                    user=user,
                    credits_assigned=credits_assigned,
                )

                # Enviar notificación al admin (best-effort, no bloquea activación)
                # Usa get_admin_notification_email() como SSOT para destinatario
                # Requiere db session para idempotencia vía admin_notification_events
                try:
                    admin_email_sent = await send_admin_activation_notice(
                        self.email_sender,
                        self.db,
                        user_email=user.user_email,
                        user_name=user.user_full_name,
                        auth_user_id=user.auth_user_id,
                        credits_assigned=credits_assigned,
                        user_id=int(user.user_id),
                        ip_address=payload.get("ip_address"),
                        user_agent=payload.get("user_agent"),
                    )
                    
                    if not admin_email_sent:
                        logger.debug(
                            "admin_activation_email_skipped auth_user_id=%s",
                            str(user.auth_user_id)[:8] + "...",
                        )
                except Exception as e:
                    logger.warning(
                        "admin_activation_email_exception auth_user_id=%s error=%s",
                        str(user.auth_user_id)[:8] + "..." if user.auth_user_id else "None",
                        str(e)[:200],
                    )

                # Log de auditoría (siempre, independiente del correo)
                try:
                    self.audit_service.log_activation_success(
                        user_id=str(user.user_id),
                        email=user.user_email,
                        ip_address=payload.get("ip_address"),
                        user_agent=payload.get("user_agent"),
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
            # Usar el servicio inyectado para enviar el email
            # DB 2.0 SSOT: Propagar auth_user_id para persistencia de eventos
            await self.welcome_email_service.send_welcome_email(
                email=user.user_email,
                full_name=user.user_full_name,
                credits_assigned=credits_assigned,
                auth_user_id=getattr(user, "auth_user_id", None),
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
        Rate limiting manejado por RateLimitDep en la ruta (no en servicio).
        
        SEGURIDAD: Siempre responde 200 con mensaje genérico para no revelar
        si el email existe, ya está activo, o no existe.

        data esperado:
            - email
            - ip_address (opcional, para auditoría)
            - user_agent (opcional, para auditoría)
        """
        payload = as_dict(data)
        email = (payload.get("email") or "").strip().lower()
        ip_address = payload.get("ip_address", "unknown")
        user_agent = payload.get("user_agent", "")
        email_masked = email[:3] + "***" if email else "unknown"

        # Mensaje genérico para TODAS las respuestas (seguridad anti-enumeración)
        generic_message = "Si existe una cuenta con ese correo y aún no ha sido activada, recibirá un nuevo enlace de activación."

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email requerido.",
            )

        # Log de request recibido
        logger.info(
            "activation_resend_requested email=%s ip=%s ua=%s",
            email_masked,
            ip_address,
            (user_agent[:50] + "...") if user_agent and len(user_agent) > 50 else user_agent,
        )

        user = await self.user_service.get_by_email(email)
        if not user:
            # No revelamos existencia - respuesta idéntica
            logger.info(
                "activation_resend_skipped_not_found email=%s ip=%s",
                email_masked,
                ip_address,
            )
            return {"message": generic_message}

        if await self.activation_service.is_active(user):
            # Ya activo - respuesta idéntica (no revelar estado)
            logger.info(
                "activation_resend_skipped_already_active user_id=%s ip=%s",
                user.user_id,
                ip_address,
            )
            return {"message": generic_message}

        # Usuario existe y no está activo -> generar token y enviar email
        # DB 2.0 SSOT: Obtener auth_user_id para propagación
        auth_user_id = getattr(user, "auth_user_id", None)
        
        token = await self.activation_service.issue_activation_token(
            user_id=str(user.user_id),
            auth_user_id=auth_user_id,
        )

        logger.info(
            "activation_resend_sent user_id=%s auth_user_id=%s ip=%s",
            user.user_id,
            (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
            ip_address,
        )

        # Envío best-effort (no falla si el email no se puede enviar)
        # DB 2.0 SSOT: Propagar auth_user_id para persistencia de eventos
        email_sent = await self._send_activation_email(
            email=user.user_email,
            full_name=user.user_full_name,
            token=token,
            user_id=int(user.user_id),
            auth_user_id=auth_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Auditoría (siempre, independiente del resultado del email)
        try:
            self.audit_service.log_activation_resend(
                user_id=str(user.user_id),
                email=user.user_email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as e:
            logger.warning(f"Audit log_activation_resend failed: {e}")

        return {"message": generic_message}

    async def _send_activation_email(
        self,
        email: str,
        full_name: str,
        token: str,
        user_id: int,
        auth_user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        Wrapper para enviar activation email (inyectable para tests).
        
        DB 2.0 SSOT: Propaga auth_user_id para persistencia de eventos.
        """
        return await send_activation_email_safely(
            self.email_sender,
            email=email,
            full_name=full_name,
            token=token,
            user_id=user_id,
            auth_user_id=auth_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )


__all__ = ["ActivationFlowService"]

# Fin del script backend/app/modules/auth/services/activation_flow_service.py
