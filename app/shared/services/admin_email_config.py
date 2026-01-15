# -*- coding: utf-8 -*-
"""
backend/app/shared/services/admin_email_config.py

Helper canónico para obtener el email de notificaciones admin.

SSOT: ADMIN_NOTIFICATION_EMAIL es la ÚNICA fuente de verdad.
Si no está configurada -> skip del envío.

Autor: DoxAI
Fecha: 2026-01-15
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_admin_notification_email() -> Optional[str]:
    """
    Obtiene el email del admin para notificaciones internas.
    
    SSOT: Solo lee ADMIN_NOTIFICATION_EMAIL.
    
    Returns:
        Email del admin o None si no está configurado.
        
    Example:
        >>> email = get_admin_notification_email()
        >>> if email:
        ...     await send_internal_email(to_email=email, ...)
        >>> else:
        ...     logger.info("admin_notify_skipped reason=no_admin_email_configured")
    """
    admin_email = os.getenv("ADMIN_NOTIFICATION_EMAIL", "").strip()
    
    if admin_email:
        return admin_email
    
    # No configurado -> skip
    return None


__all__ = ["get_admin_notification_email"]
