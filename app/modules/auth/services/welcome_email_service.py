# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/welcome_email_service.py

Servicio de envío de correos de bienvenida.
Abstrae la lógica de envío para facilitar testing e inyección de dependencias.

Autor: DoxAI
Fecha: 2025-12-22
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

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
    ) -> bool:
        """Envía correo de bienvenida. Retorna True si se envió correctamente."""
        ...


class WelcomeEmailService:
    """
    Servicio de envío de correos de bienvenida.
    
    Encapsula la lógica de envío usando EmailSender y helpers.
    Diseñado para ser inyectable en ActivationFlowService.
    """
    
    def __init__(self, email_sender: EmailSender) -> None:
        self.email_sender = email_sender
    
    async def send_welcome_email(
        self,
        *,
        email: str,
        full_name: Optional[str],
        credits_assigned: int,
    ) -> bool:
        """
        Envía correo de bienvenida al usuario.
        
        Args:
            email: Dirección de correo del usuario
            full_name: Nombre completo del usuario (opcional)
            credits_assigned: Créditos asignados al activar
            
        Returns:
            True si se envió correctamente, False en caso de error.
        """
        try:
            await send_welcome_email_safely(
                self.email_sender,
                email=email,
                full_name=full_name,
                credits_assigned=credits_assigned,
            )
            logger.info(
                "welcome_email_service_sent email=%s credits=%d",
                email[:3] + "***",
                credits_assigned,
            )
            return True
        except Exception as e:
            logger.error(
                "welcome_email_service_failed email=%s error=%s",
                email[:3] + "***",
                str(e)[:200],
            )
            return False


__all__ = ["WelcomeEmailService", "IWelcomeEmailService"]
