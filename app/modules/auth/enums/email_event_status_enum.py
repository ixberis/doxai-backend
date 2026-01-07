# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/enums/email_event_status_enum.py

Estados de eventos de email de autenticación - fuente de verdad.

Estos valores corresponden al enum `auth_email_event_status` en Postgres.
Incluye estados operativos (envío) y de entregabilidad (webhooks).

Autor: Sistema
Fecha: 2026-01-06
"""
from enum import StrEnum
from typing import Tuple


class AuthEmailEventStatus(StrEnum):
    """Enum con estados de eventos de email."""
    # Estados operativos (envío desde backend)
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    
    # Estados de entregabilidad (webhooks)
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    COMPLAINED = "complained"


# Tupla para uso en queries (sin pending, que es transitorio)
EMAIL_OPERATIONAL_STATUSES: Tuple[str, ...] = ("sent", "failed")
EMAIL_DELIVERABILITY_STATUSES: Tuple[str, ...] = ("delivered", "bounced", "complained")
ALL_EMAIL_EVENT_STATUSES: Tuple[str, ...] = tuple(e.value for e in AuthEmailEventStatus)

# Estados que implican que el correo fue enviado al proveedor (para conteos de "enviados")
# Incluye delivered/bounced/complained porque son estados monotónicos que suceden DESPUÉS de sent
EMAIL_SENT_LIKE_STATUSES: Tuple[str, ...] = ("sent", "delivered", "bounced", "complained")


__all__ = [
    "AuthEmailEventStatus",
    "EMAIL_OPERATIONAL_STATUSES",
    "EMAIL_DELIVERABILITY_STATUSES",
    "ALL_EMAIL_EVENT_STATUSES",
    "EMAIL_SENT_LIKE_STATUSES",
]

# Fin del archivo
