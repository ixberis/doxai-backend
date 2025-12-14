
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/activity_stats_service.py

Servicios de agregación ligera de actividad de archivos PRODUCTO.

Objetivo:
- Proveer un resumen sencillo de actividad en el módulo Files por proyecto,
  sin depender todavía del subsistema completo de métricas (Prometheus,
  vistas SQL, etc.), que se abordará en la fase de métricas/observabilidad.

Responsabilidades:
- Contar eventos por tipo (ProductFileEvent) en una ventana de tiempo.
- Devolver un dict amigable para ser serializado a JSON.

Decisiones Files v2:
- Async only (AsyncSession).
- Trabaja directamente sobre ProductFileActivity.
- No realiza joins complejos; para KPIs avanzadas se usará el módulo
  `metrics/` en fases posteriores.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.files.enums import ProductFileEvent
from app.modules.files.models.product_file_activity_models import ProductFileActivity


async def get_project_activity_stats(
    session: AsyncSession,
    *,
    project_id: UUID,
    days_back: int = 7,
) -> Dict[str, int]:
    """
    Devuelve un resumen simple de actividad para un proyecto en los últimos
    `days_back` días.

    Retorna un dict del tipo:
        {
            "total_events": 42,
            "by_event_type": {
                "download": 20,
                "preview": 10,
                "regenerate": 12
            }
        }

    NOTA:
    - La lógica detallada de KPIs (vistas SQL, tasas, etc.) se hará en el
      módulo `metrics/` en una fase posterior.
    """
    days = max(1, min(90, int(days_back)))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Conteos por tipo de evento
    stmt = (
        select(
            ProductFileActivity.event_type,
            func.count(ProductFileActivity.activity_id),
        )
        .where(
            ProductFileActivity.project_id == project_id,
            ProductFileActivity.event_at >= cutoff,
        )
        .group_by(ProductFileActivity.event_type)
    )
    result = await session.execute(stmt)
    rows = result.all()

    by_event_type: Dict[str, int] = {}
    total_events = 0

    for event_type, count in rows:
        key = (
            event_type.value
            if isinstance(event_type, ProductFileEvent)
            else str(event_type)
        )
        count_int = int(count or 0)
        by_event_type[key] = count_int
        total_events += count_int

    return {
        "total_events": total_events,
        "by_event_type": by_event_type,
    }


class ActivityStatsService:
    """
    Clase wrapper para estadísticas de actividad (compatibilidad con tests).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def aggregate_by_event_type(
        self,
        project_id: UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Dict[ProductFileEvent, int]:
        """
        Agrega eventos por tipo para un proyecto.
        """
        stmt = (
            select(
                ProductFileActivity.event_type,
                func.count(ProductFileActivity.product_file_activity_id).label("count"),
            )
            .where(ProductFileActivity.project_id == project_id)
            .group_by(ProductFileActivity.event_type)
        )

        if date_from:
            stmt = stmt.where(ProductFileActivity.event_at >= date_from)
        if date_to:
            stmt = stmt.where(ProductFileActivity.event_at <= date_to)

        result = await self.db.execute(stmt)
        rows = result.all()

        return {row.event_type: row.count for row in rows}

    async def aggregate_by_day(
        self,
        project_id: UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Dict[str, int]:
        """
        Agrega eventos por día para un proyecto.
        """
        stmt = (
            select(
                func.date(ProductFileActivity.event_at).label("day"),
                func.count(ProductFileActivity.product_file_activity_id).label("count"),
            )
            .where(ProductFileActivity.project_id == project_id)
            .group_by(func.date(ProductFileActivity.event_at))
        )

        if date_from:
            stmt = stmt.where(ProductFileActivity.event_at >= date_from)
        if date_to:
            stmt = stmt.where(ProductFileActivity.event_at <= date_to)

        result = await self.db.execute(stmt)
        rows = result.all()

        return {str(row.day): row.count for row in rows}

    async def recent_activity(
        self,
        project_id: UUID,
        limit: int = 50,
    ) -> list:
        """
        Obtiene actividad reciente de un proyecto.
        
        Args:
            project_id: ID del proyecto
            limit: Número máximo de eventos a retornar
            
        Returns:
            Lista de eventos recientes con detalles
        """
        stmt = (
            select(ProductFileActivity)
            .where(ProductFileActivity.project_id == project_id)
            .order_by(ProductFileActivity.event_at.desc())
            .limit(limit)
        )
        
        result = await self.db.execute(stmt)
        activities = result.scalars().all()
        
        return [
            {
                "event_type": activity.event_type.value if hasattr(activity.event_type, 'value') else str(activity.event_type),
                "event_at": activity.event_at,
                "file_name": getattr(activity, 'file_name', None),
                "file_path": getattr(activity, 'file_path', None),
                "file_size": getattr(activity, 'file_size', None),
                "mime_type": getattr(activity, 'mime_type', None),
            }
            for activity in activities
        ]


__all__ = ["get_project_activity_stats", "ActivityStatsService"]

# Fin del archivo backend/app/modules/files/services/activity_stats_service.py
