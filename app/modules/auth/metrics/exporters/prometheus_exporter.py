
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/exporters/prometheus_exporter.py

Exportador Prometheus para métricas del módulo Auth.

Actúa como bridge entre:
- Agregadores SQL (AuthAggregators)
- Coleccionistas Prometheus (auth_collectors)

Su función principal es actualizar gauges derivados
como sesiones activas y ratio de conversión.

Autor: Ixchel Beristain
Fecha: 2025-11-07
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.metrics.aggregators.auth_aggregators import AuthAggregators
from app.modules.auth.metrics.collectors.auth_collectors import (
    auth_activation_conversion_ratio,
    auth_active_sessions,
)


class AuthPrometheusExporter:
    """
    Bridge entre agregadores (consulta SQL) y collectors (Prometheus).
    Útil para refrescar gauges/ratios en momentos clave o con un cron.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agg = AuthAggregators(db)

    async def refresh_gauges(self) -> dict:
        """Refresca gauges derivados desde la BD y actualiza Prometheus."""
        active = await self.agg.get_active_sessions()
        ratio = await self.agg.get_latest_activation_conversion_ratio()

        auth_active_sessions.set(active)
        auth_activation_conversion_ratio.set(ratio)

        return {"active_sessions": active, "activation_conversion_ratio": ratio}


# Fin del archivo backend/app/modules/auth/metrics/exporters/prometheus_exporter.py
