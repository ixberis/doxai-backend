
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/analytics/activity_stats_service.py

Agregaciones de actividad sobre product_file_activity:
- aggregate_by_event_type(project_id, date_from, date_to)
- recent_activity(project_id, limit)

Trabaja directo con el ORM y agrupa en SQL para eficiencia.
Compatible con Session y AsyncSession.

Autor: DoxAI
Fecha: 2025-11-10
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession


class ActivityStatsService:
    """Agregaciones de actividad para dashboards del módulo Files."""

    def __init__(self, db: Session | AsyncSession):
        self.db = db

    async def _exec(self, stmt):
        result = self.db.execute(stmt)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    async def aggregate_by_event_type(
        self,
        project_id,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """
        Devuelve {event_type: count} como strings serializables.
        """
        from app.modules.files.models import ProductFileActivity

        stmt = (
            select(ProductFileActivity.event_type, func.count().label("n"))
            .where(ProductFileActivity.project_id == project_id)
        )
        if date_from:
            stmt = stmt.where(ProductFileActivity.event_at >= date_from)
        if date_to:
            stmt = stmt.where(ProductFileActivity.event_at <= date_to)
        stmt = stmt.group_by(ProductFileActivity.event_type)

        rows = (await self._exec(stmt)).all()
        out: Dict[str, int] = {}
        for ev, n in rows:
            key = getattr(ev, "value", None) or getattr(ev, "name", None) or str(ev)
            out[key] = int(n or 0)
        return out

    async def recent_activity(self, project_id, limit: int = 50) -> List[dict]:
        """
        Últimos eventos para la tarjeta de actividad reciente del proyecto.
        Incluye: event_type, event_at, display_name, storage_path, size, mime.
        """
        from app.modules.files.models import ProductFileActivity

        stmt = (
            select(
                ProductFileActivity.event_type,
                ProductFileActivity.event_at,
                ProductFileActivity.product_file_display_name,
                ProductFileActivity.product_file_storage_path,
                ProductFileActivity.product_file_size_bytes,
                ProductFileActivity.product_file_mime_type,
            )
            .where(ProductFileActivity.project_id == project_id)
            .order_by(ProductFileActivity.event_at.desc())
            .limit(max(1, min(500, int(limit))))
        )
        rows = (await self._exec(stmt)).all()
        out: List[dict] = []
        for ev, ts, name, path, size, mime in rows:
            out.append(
                {
                    "event_type": getattr(ev, "value", None) or getattr(ev, "name", None) or str(ev),
                    "event_at": ts,
                    "display_name": name,
                    "storage_path": path,
                    "size_bytes": size,
                    "mime_type": mime,
                }
            )
        return out


# Fin del archivo backend/app/modules/files/services/analytics/activity_stats_service.py
