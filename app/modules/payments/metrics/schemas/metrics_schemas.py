
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/schemas/metrics_schemas.py

Schemas Pydantic para respuestas de métricas.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class LatencyStats(BaseModel):
    """Estadísticas de latencia."""
    p50: float = Field(description="Percentil 50 (mediana) en ms")
    p95: float = Field(description="Percentil 95 en ms")
    p99: float = Field(description="Percentil 99 en ms")
    avg: float = Field(description="Promedio en ms")


class EndpointMetrics(BaseModel):
    """Métricas de un endpoint específico."""
    endpoint: str
    total_requests: int = Field(description="Total de requests")
    total_errors: int = Field(description="Total de errores")
    error_rate: float = Field(description="Tasa de error (%)")
    latency: LatencyStats
    errors_by_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Errores agrupados por tipo"
    )


class ProviderConversionMetrics(BaseModel):
    """Métricas de conversión de un proveedor."""
    provider: str
    total_attempts: int = Field(description="Total de intentos")
    successful: int = Field(description="Pagos exitosos")
    failed: int = Field(description="Pagos fallidos")
    pending: int = Field(description="Pagos pendientes")
    cancelled: int = Field(description="Pagos cancelados")
    conversion_rate: float = Field(description="Tasa de conversión (%)")
    failure_rate: float = Field(description="Tasa de fallo (%)")


class MetricsSnapshot(BaseModel):
    """Snapshot de métricas en un momento dado."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    time_window_hours: int = Field(description="Ventana de tiempo en horas")
    endpoints: List[EndpointMetrics] = Field(default_factory=list)
    providers: List[ProviderConversionMetrics] = Field(default_factory=list)


class MetricsSummary(BaseModel):
    """Resumen general del sistema."""
    uptime_seconds: float
    uptime_hours: float
    total_endpoints_tracked: int
    total_providers_tracked: int
    last_hour_stats: Dict = Field(
        description="Estadísticas de la última hora",
        default_factory=dict
    )


class AlertLevel(str):
    """Niveles de alerta."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class HealthAlert(BaseModel):
    """Alerta de salud del sistema."""
    level: str = Field(description="Nivel de alerta: info, warning, critical")
    message: str = Field(description="Mensaje descriptivo")


class HealthStatus(BaseModel):
    """Estado de salud del sistema de pagos."""
    status: str = Field(description="Estado general: healthy, warning, critical")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    alerts: List[HealthAlert] = Field(default_factory=list)
    metrics_summary: MetricsSummary


class MetricsQueryRequest(BaseModel):
    """Request para consulta de métricas."""
    endpoint: Optional[str] = Field(None, description="Filtrar por endpoint")
    provider: Optional[str] = Field(None, description="Filtrar por proveedor")
    hours: int = Field(1, ge=1, le=24, description="Ventana de tiempo en horas")


class MetricsResponse(BaseModel):
    """Respuesta genérica de métricas."""
    success: bool = True
    data: Dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Rebuild models para resolver referencias forward
HealthStatus.model_rebuild()

# Fin del archivo backend\app\modules\payments\metrics\schemas\metrics_schemas.py