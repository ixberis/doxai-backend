# -*- coding: utf-8 -*-
"""
backend/app/shared/enums/email_status_enum.py

Estados de envío y entregabilidad de correo (DB-backed).
Usar en user_email_logs.email_status.

Incluye estados operativos (sent/failed/queued/skipped) y de engagement
(delivered/opened/bounced/complained/suppressed/unsubscribed) para métricas
de entregabilidad y seguimiento de campañas.

Autor: Ixchel Beristain
Actualizado: 23/10/2025
"""

from enum import StrEnum
from typing import Any
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM


class EmailStatus(StrEnum):
    # === Estados operativos (envío) ===
    SENT = "sent"
    FAILED = "failed"
    QUEUED = "queued"
    SKIPPED = "skipped"
    
    # === Estados de entregabilidad y engagement ===
    DELIVERED = "delivered"      # Confirmación de entrega al MTA destino
    OPENED = "opened"            # Pixel de tracking activado
    BOUNCED = "bounced"          # Rebote (hard/soft)
    COMPLAINED = "complained"    # Marcado como spam
    SUPPRESSED = "suppressed"    # Dirección en lista de supresión
    UNSUBSCRIBED = "unsubscribed"  # Usuario se dio de baja


def as_pg_enum(name: str = "email_status_enum", schema: str | None = None):
    from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
    pg = PG_ENUM(
        *[e.value for e in EmailStatus],  # ← valores posicionales (minúsculas)
        name=name,
        schema=schema,
        create_type=False,
    )
    pg.enum_class = EmailStatus
    return pg


__all__ = ["EmailStatus", "as_pg_enum"]
# Fin del script







