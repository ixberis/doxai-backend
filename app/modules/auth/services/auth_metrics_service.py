
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/services/auth_metrics_service.py

Orquestador de métricas del módulo Auth. Coordina la actualización de gauges,
ratios y contadores a partir de vistas SQL y collectors Prometheus. Permite
sincronizar métricas de negocio (sesiones activas, tasa de conversión de
activaciones, intentos de login) con los collectors en memoria.

Autor: Ixchel Beristain
Fecha: 07/11/2025
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.metrics.aggregators.auth_aggregators import AuthAggregators
from app.modules.auth.metrics.collectors.auth_collectors import (
    auth_activation_conversion_ratio,
    auth_active_sessions,
    auth_login_attempts_total,
)

class AuthMetricsService:
    """
    Orquestador de métricas de Auth.
    - Refresca gauges derivados desde BD
    - "Backfill" ligero de intentos por ventana de tiempo (opcional para dashboard)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agg = AuthAggregators(db)

    async def refresh_gauges(self) -> Dict[str, Any]:
        active = await self.agg.get_active_sessions()
        ratio = await self.agg.get_latest_activation_conversion_ratio()
        auth_active_sessions.set(active)
        auth_activation_conversion_ratio.set(ratio)
        return {"active_sessions": active, "activation_conversion_ratio": ratio}

    async def backfill_login_attempts_window(
        self,
        *,
        minutes: int = 60,
        now: Optional[datetime] = None
    ) -> int:
        """
        Consulta f_auth_login_attempts_hourly y aplica a Counter con labels.
        Útil para "re-jalar" una ventana breve en arranques del proceso.
        """
        _now = now or datetime.now(timezone.utc)
        start = _now - timedelta(minutes=minutes)
        rows = await self.agg.get_login_attempts_hourly(start, _now)
        count = 0
        for ts_hour, success, reason, attempts in rows:
            # Sanear labels (evitar None/PII/alto cardinalidad)
            success_label = "true" if bool(success) else "false"
            reason_label = (reason or "none")
            try:
                auth_login_attempts_total.labels(
                    success=success_label,
                    reason=reason_label
                ).inc(int(attempts))
                count += int(attempts)
            except Exception:
                # No romper el servicio de métricas por labels raros
                continue
        return count

# Fin del archivo backend/app/modules/auth/metrics/services/auth_metrics_service.py
