# -*- coding: utf-8 -*-
"""
backend/app/shared/services/admin_notifications.py

Servicio unificado para notificaciones al admin con idempotencia persistente.

Todos los métodos usan:
- get_admin_notification_email() como SSOT para destinatario
- send_internal_email() para envío (sin tracking en auth_email_events)
- Idempotencia via admin_notification_events (DB)
- Best-effort: errores no bloquean flujos de negocio

IMPORTANTE: Este módulo NO hace commit/rollback.
El caller (registration_flow_service, activation_flow_service) es responsable
del unit-of-work y decide cuándo hacer commit().

Autor: DoxAI
Fecha: 2026-01-15
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.services.admin_email_config import get_admin_notification_email
from app.shared.integrations.email_templates import render_email

if TYPE_CHECKING:
    from app.shared.integrations.email_sender import IEmailSender

logger = logging.getLogger(__name__)


async def _claim_notification_slot(
    db: AsyncSession,
    event_key: str,
    event_type: str,
    auth_user_id: UUID,
    related_id: Optional[int] = None,
) -> bool:
    """
    Intenta reservar un slot de notificación (idempotencia).
    
    Usa INSERT con ON CONFLICT DO NOTHING para atomicidad.
    Solo retorna True si se insertó (ganamos la carrera).
    
    NOTA: Solo hace execute() + flush(). NO hace commit/rollback.
    El caller es responsable del unit-of-work.
    
    Args:
        db: Sesión de base de datos
        event_key: Llave única (ej: "signup:{auth_user_id}")
        event_type: Tipo de evento (signup/activation)
        auth_user_id: UUID del usuario
        related_id: ID relacionado opcional
        
    Returns:
        True si se reservó el slot (debemos enviar), False si ya existe.
    """
    try:
        result = await db.execute(
            text("""
                INSERT INTO public.admin_notification_events 
                    (event_key, event_type, auth_user_id, related_id, status)
                VALUES 
                    (:event_key, :event_type, :auth_user_id, :related_id, 'pending')
                ON CONFLICT (event_key) DO NOTHING
                RETURNING id
            """),
            {
                "event_key": event_key,
                "event_type": event_type,
                "auth_user_id": auth_user_id,
                "related_id": related_id,
            }
        )
        row = result.fetchone()
        
        if row:
            await db.flush()
            logger.debug(
                "admin_notification_slot_claimed event_key=%s id=%s",
                event_key,
                row[0],
            )
            return True
        else:
            logger.info(
                "admin_notification_already_exists event_key=%s",
                event_key,
            )
            return False
            
    except Exception as e:
        logger.warning(
            "admin_notification_claim_error event_key=%s error=%s",
            event_key,
            str(e)[:200],
        )
        return False


async def _mark_notification_sent(
    db: AsyncSession,
    event_key: str,
    provider_message_id: Optional[str] = None,
) -> None:
    """
    Marca la notificación como enviada exitosamente.
    
    NOTA: Solo hace execute() + flush(). NO hace commit.
    """
    try:
        await db.execute(
            text("""
                UPDATE public.admin_notification_events
                SET status = 'sent',
                    sent_at = now(),
                    provider_message_id = :provider_message_id
                WHERE event_key = :event_key
            """),
            {
                "event_key": event_key,
                "provider_message_id": provider_message_id,
            }
        )
        await db.flush()
    except Exception as e:
        logger.warning(
            "admin_notification_mark_sent_error event_key=%s error=%s",
            event_key,
            str(e)[:200],
        )


async def _release_notification_slot(
    db: AsyncSession,
    event_key: str,
    error_message: Optional[str] = None,
) -> None:
    """
    Libera el slot si el envío falló (permite reintento futuro).
    
    Usamos DELETE para permitir retries sin cooldown.
    
    NOTA: Solo hace execute() + flush(). NO hace commit/rollback.
    """
    try:
        await db.execute(
            text("""
                DELETE FROM public.admin_notification_events
                WHERE event_key = :event_key AND status = 'pending'
            """),
            {"event_key": event_key}
        )
        await db.flush()
        logger.debug(
            "admin_notification_slot_released event_key=%s reason=%s",
            event_key,
            (error_message[:100] if error_message else "unknown"),
        )
    except Exception as e:
        logger.warning(
            "admin_notification_release_error event_key=%s error=%s",
            event_key,
            str(e)[:100],
        )


async def send_admin_signup_notice(
    email_sender: "IEmailSender",
    db: AsyncSession,
    *,
    user_email: str,
    user_name: Optional[str],
    auth_user_id: UUID,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """
    Envía notificación al admin cuando un usuario se registra.
    
    Idempotente: usa admin_notification_events para evitar duplicados.
    Best-effort: no lanza excepción, retorna False si falla.
    
    NOTA: NO hace commit. El caller es responsable del unit-of-work.
    
    Args:
        email_sender: Implementación de IEmailSender
        db: Sesión de base de datos (para idempotencia)
        user_email: Email del usuario que se registró
        user_name: Nombre del usuario
        auth_user_id: UUID del usuario (SSOT)
        user_id: ID legacy del usuario (opcional)
        ip_address: IP del registro
        user_agent: User agent del navegador
        
    Returns:
        True si se envió correctamente, False en caso contrario.
    """
    admin_email = get_admin_notification_email()
    event_key = f"signup:{auth_user_id}"
    
    if not admin_email:
        logger.info(
            "admin_notify_skipped reason=no_admin_email_configured event=signup "
            "user=%s",
            (user_email[:3] + "***") if user_email else "unknown",
        )
        return False
    
    # Idempotencia: intentar claim
    claimed = await _claim_notification_slot(
        db=db,
        event_key=event_key,
        event_type="signup",
        auth_user_id=auth_user_id,
        related_id=user_id,
    )
    
    if not claimed:
        logger.info(
            "admin_signup_notice_skipped reason=already_sent auth_user_id=%s",
            str(auth_user_id)[:8] + "...",
        )
        return False
    
    try:
        registration_datetime = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        context = {
            "user_email": user_email,
            "user_name": user_name or "No especificado",
            "auth_user_id": str(auth_user_id),
            "registration_datetime": registration_datetime,
            "ip_address": ip_address or "N/A",
            "user_agent": user_agent or "N/A",
            "current_year": datetime.now(timezone.utc).year,
        }
        
        html, text_body, used_template = render_email("admin_signup_notice", context)
        
        if not text_body:
            text_body = _build_signup_fallback_text(context)
        if not html:
            import html as html_lib
            html = f"<pre>{html_lib.escape(text_body)}</pre>"
        
        subject = f"[DoxAI] Nuevo registro: {user_email}"
        
        message_id = await email_sender.send_internal_email(
            to_email=admin_email,
            subject=subject,
            html_body=html,
            text_body=text_body,
        )
        
        # Éxito: marcar como enviado (solo flush, NO commit)
        await _mark_notification_sent(db, event_key, message_id)
        
        logger.info(
            "admin_signup_notice_sent to=%s user=%s auth_user_id=%s message_id=%s",
            admin_email[:3] + "***",
            (user_email[:3] + "***") if user_email else "unknown",
            str(auth_user_id)[:8] + "...",
            message_id,
        )
        return True
        
    except Exception as e:
        # Fallo: liberar slot para permitir reintento (solo flush, NO rollback)
        await _release_notification_slot(db, event_key, str(e))
        
        logger.warning(
            "admin_signup_notice_failed to=%s user=%s error=%s",
            (admin_email[:3] + "***") if admin_email else "None",
            (user_email[:3] + "***") if user_email else "unknown",
            str(e)[:200],
        )
        return False


async def send_admin_activation_notice(
    email_sender: "IEmailSender",
    db: AsyncSession,
    *,
    user_email: str,
    user_name: Optional[str],
    auth_user_id: UUID,
    credits_assigned: int,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """
    Envía notificación al admin cuando un usuario activa su cuenta.
    
    Idempotente: usa admin_notification_events para evitar duplicados.
    Best-effort: no lanza excepción, retorna False si falla.
    
    NOTA: NO hace commit. El caller es responsable del unit-of-work.
    
    Args:
        email_sender: Implementación de IEmailSender
        db: Sesión de base de datos (para idempotencia)
        user_email: Email del usuario activado
        user_name: Nombre del usuario
        auth_user_id: UUID del usuario (SSOT)
        credits_assigned: Créditos asignados
        user_id: ID legacy del usuario (opcional)
        ip_address: IP de la activación
        user_agent: User agent del navegador
        
    Returns:
        True si se envió correctamente, False en caso contrario.
    """
    admin_email = get_admin_notification_email()
    event_key = f"activation:{auth_user_id}"
    
    if not admin_email:
        logger.info(
            "admin_notify_skipped reason=no_admin_email_configured event=activation "
            "auth_user_id=%s",
            str(auth_user_id)[:8] + "...",
        )
        return False
    
    # Idempotencia: intentar claim
    claimed = await _claim_notification_slot(
        db=db,
        event_key=event_key,
        event_type="activation",
        auth_user_id=auth_user_id,
        related_id=user_id,
    )
    
    if not claimed:
        logger.info(
            "admin_activation_notice_skipped reason=already_sent auth_user_id=%s",
            str(auth_user_id)[:8] + "...",
        )
        return False
    
    try:
        activation_datetime = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        context = {
            "user_email": user_email,
            "user_name": user_name or "No especificado",
            "auth_user_id": str(auth_user_id),
            "user_id": str(user_id) if user_id else "N/A",
            "credits_assigned": credits_assigned,
            "activation_datetime": activation_datetime,
            "ip_address": ip_address or "N/A",
            "user_agent": user_agent or "N/A",
            "current_year": datetime.now(timezone.utc).year,
        }
        
        html, text_body, used_template = render_email("admin_activation_notice", context)
        
        if not text_body:
            text_body = _build_activation_fallback_text(context)
        if not html:
            import html as html_lib
            html = f"<pre>{html_lib.escape(text_body)}</pre>"
        
        subject = f"[DoxAI] Cuenta activada: {user_email}"
        
        message_id = await email_sender.send_internal_email(
            to_email=admin_email,
            subject=subject,
            html_body=html,
            text_body=text_body,
        )
        
        # Éxito: marcar como enviado (solo flush, NO commit)
        await _mark_notification_sent(db, event_key, message_id)
        
        logger.info(
            "admin_activation_notice_sent to=%s auth_user_id=%s credits=%d message_id=%s",
            admin_email[:3] + "***",
            str(auth_user_id)[:8] + "...",
            credits_assigned,
            message_id,
        )
        return True
        
    except Exception as e:
        # Fallo: liberar slot para permitir reintento (solo flush, NO rollback)
        await _release_notification_slot(db, event_key, str(e))
        
        logger.warning(
            "admin_activation_notice_failed to=%s auth_user_id=%s error=%s",
            (admin_email[:3] + "***") if admin_email else "None",
            str(auth_user_id)[:8] + "...",
            str(e)[:200],
        )
        return False


def _build_signup_fallback_text(context: dict) -> str:
    """Texto plano de fallback para signup notice."""
    return f"""=== NUEVO REGISTRO - DoxAI ===

Email: {context['user_email']}
Nombre: {context['user_name']}
auth_user_id: {context['auth_user_id']}
Fecha: {context['registration_datetime']} UTC
IP: {context['ip_address']}

---
Notificación automática de DoxAI
"""


def _build_activation_fallback_text(context: dict) -> str:
    """Texto plano de fallback para activation notice."""
    return f"""=== CUENTA ACTIVADA - DoxAI ===

Email: {context['user_email']}
Nombre: {context['user_name']}
auth_user_id: {context['auth_user_id']}
Créditos asignados: {context['credits_assigned']}
Fecha: {context['activation_datetime']} UTC

---
Notificación automática de DoxAI
"""


__all__ = [
    "send_admin_signup_notice",
    "send_admin_activation_notice",
]
