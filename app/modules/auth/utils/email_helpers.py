
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/utils/email_helpers.py

Helpers de alto nivel para envío de correos relacionados con Auth
(activación, bienvenida, restablecimiento de contraseña, notificación admin).

DB 2.0 SSOT: Todos los helpers ahora aceptan auth_user_id para garantizar
que los eventos de email se persistan correctamente.

Autor: Ixchel Beristain
Fecha: 19/11/2025
Actualizado: 2026-01-13 - SSOT auth_user_id propagation
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status

from app.shared.integrations.email_sender import IEmailSender

logger = logging.getLogger(__name__)


async def send_activation_email_or_raise(
    email_sender: IEmailSender,
    *,
    email: str,
    full_name: Optional[str],
    token: str,
    auth_user_id: Optional[UUID] = None,
) -> None:
    """
    Envía correo de activación y lanza HTTPException si falla.
    
    DB 2.0: Propaga auth_user_id al sender para persistencia de eventos.
    """
    try:
        await email_sender.send_activation_email(
            to_email=email,
            full_name=full_name or "",
            activation_token=token,
            auth_user_id=auth_user_id,
        )
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - protección extra
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No fue posible enviar el correo de activación: {e}",
        )


async def send_welcome_email_safely(
    email_sender: IEmailSender,
    *,
    email: str,
    full_name: Optional[str],
    credits_assigned: int,
    auth_user_id: Optional[UUID] = None,
) -> None:
    """
    Envía correo de bienvenida. No lanza excepción hacia arriba,
    solo ignora el error (el caller puede hacer logging si lo requiere).
    
    DB 2.0: Propaga auth_user_id al sender para persistencia de eventos.
    """
    try:
        await email_sender.send_welcome_email(
            to_email=email,
            full_name=full_name or "",
            credits_assigned=credits_assigned,
            auth_user_id=auth_user_id,
        )
    except Exception:
        return


async def send_activation_email_safely(
    email_sender: IEmailSender,
    *,
    email: str,
    full_name: Optional[str],
    token: str,
    user_id: Optional[int] = None,
    auth_user_id: Optional[UUID] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """
    Envía correo de activación (reenvío) de forma best-effort.
    
    No lanza excepción hacia arriba. Loggea el resultado.
    
    DB 2.0: Propaga auth_user_id al sender para persistencia de eventos.
    
    Logs:
        - activation_resend_email_sent to=... user_id=...
        - activation_resend_email_failed to=... user_id=... error=...
    
    Args:
        email_sender: Implementación de IEmailSender
        email: Email destino
        full_name: Nombre del usuario
        token: Token de activación
        user_id: ID del usuario (para logs, legacy)
        auth_user_id: UUID del usuario (SSOT para eventos de email)
        ip_address: IP del usuario (para logs)
        user_agent: User agent (para logs)
    
    Returns:
        True si el email se envió correctamente, False en caso contrario.
    """
    email_masked = email[:3] + "***" if email else "unknown"
    
    try:
        await email_sender.send_activation_email(
            to_email=email,
            full_name=full_name or "",
            activation_token=token,
            auth_user_id=auth_user_id,
        )
        
        logger.info(
            "activation_resend_email_sent to=%s user_id=%s auth_user_id=%s ip=%s",
            email_masked,
            user_id,
            (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
            ip_address or "unknown",
        )
        return True
        
    except Exception as e:
        logger.warning(
            "activation_resend_email_failed to=%s user_id=%s auth_user_id=%s ip=%s error=%s",
            email_masked,
            user_id,
            (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
            ip_address or "unknown",
            str(e)[:200],
        )
        return False


async def send_password_reset_email_or_raise(
    email_sender: IEmailSender,
    *,
    email: str,
    full_name: Optional[str],
    reset_token: str,
    auth_user_id: Optional[UUID] = None,
) -> None:
    """
    Envía correo de restablecimiento y lanza HTTPException si falla.
    
    DB 2.0: Propaga auth_user_id al sender para persistencia de eventos.
    """
    try:
        await email_sender.send_password_reset_email(
            to_email=email,
            full_name=full_name or "",
            reset_token=reset_token,
            auth_user_id=auth_user_id,
        )
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No fue posible enviar el correo de restablecimiento: {e}",
        )


async def send_admin_activation_notice_safely(
    email_sender: IEmailSender,
    *,
    admin_email: str,
    user_email: str,
    user_name: Optional[str],
    user_id: int,
    credits_assigned: int,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    auth_user_id: Optional[UUID] = None,
) -> bool:
    """
    Envía notificación al admin cuando un usuario activa su cuenta.
    
    Best-effort: no lanza excepción, solo retorna False si falla.
    Loggea warning con contexto si falla.
    
    DB 2.0: Propaga auth_user_id (del usuario activado) para tracking en auth_email_events.
    
    Args:
        email_sender: Implementación de IEmailSender
        admin_email: Email del admin destino (normalmente desde settings)
        user_email: Email del usuario que activó
        user_name: Nombre del usuario
        user_id: ID del usuario
        credits_assigned: Créditos asignados
        ip_address: IP del usuario (opcional)
        user_agent: User agent del navegador (opcional)
        auth_user_id: UUID del usuario activado (para tracking)
    
    Returns:
        True si el email se envió correctamente, False en caso contrario.
    """
    try:
        activation_datetime = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        await email_sender.send_admin_activation_notice(
            to_email=admin_email,
            user_email=user_email,
            user_name=user_name or "No especificado",
            user_id=str(user_id),
            credits_assigned=credits_assigned,
            ip_address=ip_address,
            user_agent=user_agent,
            activation_datetime_utc=activation_datetime,
            auth_user_id=auth_user_id,
        )
        
        logger.info(
            "admin_activation_email_sent to=%s user=%s user_id=%s credits=%d",
            admin_email,
            user_email[:3] + "***" if user_email else "unknown",
            user_id,
            credits_assigned,
        )
        return True
        
    except Exception as e:
        logger.warning(
            "admin_activation_email_failed to=%s user=%s user_id=%s error=%s",
            admin_email,
            user_email[:3] + "***" if user_email else "unknown",
            user_id,
            str(e)[:200],
        )
        return False


__all__ = [
    "send_activation_email_or_raise",
    "send_activation_email_safely",
    "send_welcome_email_safely",
    "send_password_reset_email_or_raise",
    "send_admin_activation_notice_safely",
]

# Fin del script backend/app/modules/auth/utils/email_helpers.py
