# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/welcome_email_service.py

Servicio de envío de correos de bienvenida.
Abstrae la lógica de envío para facilitar testing e inyección de dependencias.

DB 2.0 SSOT: Propaga auth_user_id para garantizar persistencia de eventos.

Autor: DoxAI
Fecha: 2025-12-22
Actualizado: 2026-01-13 - SSOT auth_user_id propagation
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol
from uuid import UUID

from app.shared.integrations.email_sender import EmailSender
from app.modules.auth.utils.email_helpers import send_welcome_email_safely

logger = logging.getLogger(__name__)


class IWelcomeEmailService(Protocol):
    """Protocolo para servicios de welcome email (para typing)."""
    
    async def send_welcome_email(
        self,
        *,
        email: str,
        full_name: Optional[str],
        credits_assigned: int,
        auth_user_id: Optional[UUID] = None,
    ) -> bool:
        """Envía correo de bienvenida. Retorna True si se envió correctamente."""
        ...


class WelcomeEmailService:
    """
    Servicio de envío de correos de bienvenida.
    
    Encapsula la lógica de envío usando EmailSender y helpers.
    Diseñado para ser inyectable en ActivationFlowService.
    
    DB 2.0 SSOT: Propaga auth_user_id al sender para persistencia de eventos.
    """
    
    def __init__(self, email_sender: EmailSender) -> None:
        self.email_sender = email_sender
    
    async def send_welcome_email(
        self,
        *,
        email: str,
        full_name: Optional[str],
        credits_assigned: int,
        auth_user_id: Optional[UUID] = None,
    ) -> bool:
        """
        Envía correo de bienvenida al usuario.
        
        Args:
            email: Dirección de correo del usuario
            full_name: Nombre completo del usuario (opcional)
            credits_assigned: Créditos asignados al activar
            auth_user_id: UUID del usuario (SSOT para eventos de email)
            
        Returns:
            True si se envió correctamente, False en caso de error.
        """
        try:
            await send_welcome_email_safely(
                self.email_sender,
                email=email,
                full_name=full_name,
                credits_assigned=credits_assigned,
                auth_user_id=auth_user_id,
            )
            logger.info(
                "welcome_email_service_sent email=%s credits=%d auth_user_id=%s",
                email[:3] + "***",
                credits_assigned,
                (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
            )
            return True
        except Exception as e:
            logger.error(
                "welcome_email_service_failed email=%s auth_user_id=%s error=%s",
                email[:3] + "***",
                (str(auth_user_id)[:8] + "...") if auth_user_id else "None",
                str(e)[:200],
            )
            return False


__all__ = ["WelcomeEmailService", "IWelcomeEmailService"]
