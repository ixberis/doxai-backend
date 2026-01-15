# -*- coding: utf-8 -*-
"""
backend/app/shared/services/__init__.py

Servicios compartidos.
"""

from .admin_email_config import (
    get_admin_notification_email,
)
from .admin_notifications import (
    send_admin_signup_notice,
    send_admin_activation_notice,
)

__all__ = [
    "get_admin_notification_email",
    "send_admin_signup_notice",
    "send_admin_activation_notice",
]
