
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/db/base.py

Helpers y utilidades comunes para agregadores que consultan BD.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def coerce_dt(dt: Optional[datetime]) -> datetime:
    """Asegura datetime con tz UTC."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def date_floor(dt: datetime) -> datetime:
    """00:00:00 del mismo día."""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def date_ceil(dt: datetime) -> datetime:
    """00:00:00 del día siguiente."""
    return (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


async def fetch_rows(db: AsyncSession, sql: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ejecuta SQL y devuelve lista de dicts (mappings)."""
    res = await db.execute(text(sql), params)
    return [dict(row) for row in res.mappings().all()]

# Fin del archivo backend\app\modules\payments\metrics\aggregators\db\base.py