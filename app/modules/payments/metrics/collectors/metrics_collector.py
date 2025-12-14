
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/collectors/metrics_collector.py

Recolector principal de métricas de pagos (usa storage en memoria).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from ..aggregators import MetricsStorage, TimeWindow

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Singleton para recolección y consulta de métricas de pagos.

    Captura:
    - Latencia de endpoints (P50, P95, P99)
    - Tasa de errores por endpoint y tipo
    - Tasas de conversión por proveedor de pago
    - Métricas agregadas en tiempo real
    """

    _instance: Optional["MetricsCollector"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, retention_hours: int = 24):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self.storage = MetricsStorage(retention_hours=retention_hours)
        self._initialized = True
        logger.info(f"MetricsCollector inicializado con retención de {retention_hours}h")

    # ----------------------------- Registro ------------------------------ #

    def record_endpoint_call(
        self,
        endpoint: str,
        latency_ms: float,
        status_code: int,
        error: Optional[str] = None,
    ) -> None:
        error_type = error
        if status_code >= 400 and not error_type:
            error_type = f"HTTP_{status_code}_{'ServerError' if status_code >= 500 else 'ClientError'}"

        self.storage.record_endpoint_call(
            endpoint=endpoint,
            latency_ms=latency_ms,
            error=error_type,
            window=TimeWindow.MINUTE,
        )

        if latency_ms > 5000:
            logger.warning(f"Latencia alta en {endpoint}: {latency_ms:.2f}ms")
        if status_code >= 500:
            logger.error(f"Error de servidor en {endpoint}: {status_code}")

    def record_payment_attempt(self, provider: str, status: str, amount_cents: Optional[int] = None) -> None:
        self.storage.record_payment_attempt(
            provider=(provider or "unknown").lower(),
            status=status or "unknown",
            window=TimeWindow.MINUTE,
        )
        if (status or "").lower() in {"failed", "error", "rejected"}:
            logger.warning(f"Pago fallido en {provider}: status={status}")

    # ----------------------------- Consulta ------------------------------ #

    def get_endpoint_metrics(self, endpoint: Optional[str] = None, hours: int = 1) -> Dict:
        since = datetime.now(timezone.utc) - timedelta(hours=hours or 1)
        return self.storage.get_endpoint_metrics(endpoint=endpoint, since=since)

    def get_provider_conversions(self, provider: Optional[str] = None, hours: int = 1) -> Dict:
        since = datetime.now(timezone.utc) - timedelta(hours=hours or 1)
        return self.storage.get_provider_conversions(provider=provider, since=since)

    def get_summary(self) -> Dict:
        return self.storage.get_summary()

    def get_health_status(self) -> Dict:
        summary = self.get_summary()
        endpoint_metrics = self.get_endpoint_metrics(hours=1)
        provider_conversions = self.get_provider_conversions(hours=1)

        alerts = []
        status = "healthy"

        # Tasa de error
        err_rate = summary["last_hour"].get("overall_error_rate", 0.0)
        if err_rate > 10:
            alerts.append({"level": "critical", "message": f"Tasa de error general muy alta: {err_rate:.2f}%"})
            status = "critical"
        elif err_rate > 5:
            alerts.append({"level": "warning", "message": f"Tasa de error elevada: {err_rate:.2f}%"})
            status = "warning" if status == "healthy" else status

        # Conversión
        conv_rate = summary["last_hour"].get("overall_conversion_rate", 0.0)
        if conv_rate < 70 and summary["last_hour"]["total_payment_attempts"] > 10:
            alerts.append({"level": "warning", "message": f"Tasa de conversión baja: {conv_rate:.2f}%"})
            status = "warning" if status == "healthy" else status

        # Latencias por endpoint
        for ep, m in endpoint_metrics.items():
            p95 = m.get("latency", {}).get("p95", 0.0)
            if p95 > 3000:
                alerts.append({"level": "warning", "message": f"Latencia alta en {ep}: P95={p95:.0f}ms"})
                status = "warning" if status == "healthy" else status

        # Fallos por proveedor
        for prov, m in provider_conversions.items():
            fr = m.get("failure_rate", 0.0)
            if fr > 20:
                alerts.append({"level": "critical", "message": f"Tasa de fallo alta en {prov}: {fr:.2f}%"})
                status = "critical"

        return {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alerts": alerts,
            "metrics_summary": summary,
        }


# Singleton global
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector

# Fin del archivo backend\app\modules\payments\metrics\collectors\metrics_collector.py
