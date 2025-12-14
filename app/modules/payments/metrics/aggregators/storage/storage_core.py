
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/storage_core.py

Implementación principal de almacenamiento de métricas en memoria.
Gestiona buckets por endpoint y proveedor con ventanas temporales.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Dict, Optional

from .time_window import TimeWindow
from .latency_bucket import LatencyBucket
from .conversion_bucket import ConversionBucket


class MetricsStorage:
    """
    Almacenamiento thread-safe de métricas operativas en memoria.

    - Endpoints: latencias, errores por tipo, p50/p95/p99/avg.
    - Proveedores: intentos/éxitos/fallos/pendientes/cancelados y tasas derivadas.
    """

    def __init__(self, retention_hours: int = 24) -> None:
        self.retention_hours = retention_hours
        self._lock = RLock()

        # endpoint -> { timestamp -> LatencyBucket }
        self._endpoint_metrics: Dict[str, Dict[datetime, LatencyBucket]] = defaultdict(
            lambda: defaultdict(LatencyBucket)
        )
        # provider -> { timestamp -> ConversionBucket }
        self._provider_conversions: Dict[str, Dict[datetime, ConversionBucket]] = defaultdict(
            lambda: defaultdict(ConversionBucket)
        )

        self._start_time = datetime.now(timezone.utc)
        self._ops = 0
        self._cleanup_every = 100  # limpieza cada N operaciones

    # --------------------------------------------------------------------- #
    # Registro
    # --------------------------------------------------------------------- #

    def record_endpoint_call(
        self,
        endpoint: str,
        latency_ms: float,
        error: Optional[str] = None,
        window: TimeWindow = TimeWindow.MINUTE,
    ) -> None:
        with self._lock:
            ts = self._window_ts(datetime.now(timezone.utc), window)
            self._endpoint_metrics[endpoint][ts].add_latency(latency_ms, error)
            self._tick_cleanup()

    def record_payment_attempt(
        self,
        provider: str,
        status: str,
        window: TimeWindow = TimeWindow.MINUTE,
    ) -> None:
        with self._lock:
            ts = self._window_ts(datetime.now(timezone.utc), window)
            self._provider_conversions[provider][ts].record_attempt(status)
            self._tick_cleanup()

    # --------------------------------------------------------------------- #
    # Consulta
    # --------------------------------------------------------------------- #

    def get_endpoint_metrics(self, endpoint: Optional[str] = None, since: Optional[datetime] = None) -> Dict[str, Dict]:
        """Agrega y devuelve métricas de endpoints desde `since` (default: 1h)."""
        with self._lock:
            since = since or (datetime.now(timezone.utc) - timedelta(hours=1))
            sources = {endpoint: self._endpoint_metrics.get(endpoint, {})} if endpoint else self._endpoint_metrics

            result: Dict[str, Dict] = {}
            for ep, buckets in sources.items():
                vals = [b for ts, b in buckets.items() if ts >= since]
                if not vals:
                    continue

                all_latencies = []
                total_requests = 0
                total_errors = 0
                errors_by_type: Dict[str, int] = defaultdict(int)

                for b in vals:
                    all_latencies.extend(b.latencies)
                    total_requests += b.total_requests
                    total_errors += b.total_errors
                    for et, n in b.error_by_type.items():
                        errors_by_type[et] += n

                latency = {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}
                if all_latencies:
                    sorted_l = sorted(all_latencies)
                    # Promedio
                    latency["avg"] = statistics.mean(sorted_l)
                    # p50/p95/p99 — reusamos cálculo del bucket (ya ordenado aquí)
                    def pct(p: float) -> float:
                        k = (len(sorted_l) - 1) * p
                        f = int(k)
                        c = f + 1
                        if c >= len(sorted_l):
                            return float(sorted_l[-1])
                        d0 = float(sorted_l[f]); d1 = float(sorted_l[c])
                        return d0 + (d1 - d0) * (k - f)

                    latency["p50"] = pct(0.50)
                    latency["p95"] = pct(0.95)
                    latency["p99"] = pct(0.99)

                result[ep] = {
                    "total_requests": total_requests,
                    "total_errors": total_errors,
                    "error_rate": (total_errors / total_requests * 100.0) if total_requests else 0.0,
                    "latency": latency,
                    "errors_by_type": dict(errors_by_type),
                }

            return result

    def get_provider_conversions(self, provider: Optional[str] = None, since: Optional[datetime] = None) -> Dict[str, Dict]:
        """Agrega y devuelve métricas de conversión por proveedor desde `since` (default: 1h)."""
        with self._lock:
            since = since or (datetime.now(timezone.utc) - timedelta(hours=1))
            sources = {provider: self._provider_conversions.get(provider, {})} if provider else self._provider_conversions

            result: Dict[str, Dict] = {}
            for prov, buckets in sources.items():
                vals = [b for ts, b in buckets.items() if ts >= since]
                if not vals:
                    continue

                total_attempts = sum(b.total_attempts for b in vals)
                successful = sum(b.successful for b in vals)
                failed = sum(b.failed for b in vals)
                pending = sum(b.pending for b in vals)
                cancelled = sum(b.cancelled for b in vals)

                result[prov] = {
                    "total_attempts": total_attempts,
                    "successful": successful,
                    "failed": failed,
                    "pending": pending,
                    "cancelled": cancelled,
                    "conversion_rate": (successful / total_attempts * 100.0) if total_attempts else 0.0,
                    "failure_rate": (failed / total_attempts * 100.0) if total_attempts else 0.0,
                }

            return result

    def get_summary(self) -> Dict:
        """Resumen general (uptime + totales última hora)."""
        with self._lock:
            now = datetime.now(timezone.utc)
            uptime_seconds = (now - self._start_time).total_seconds()

            since_one_hour = now - timedelta(hours=1)
            ep_stats = self.get_endpoint_metrics(since=since_one_hour)
            total_ep_requests = sum(s["total_requests"] for s in ep_stats.values())
            total_ep_errors = sum(s["total_errors"] for s in ep_stats.values())

            conv_stats = self.get_provider_conversions(since=since_one_hour)
            total_attempts = sum(s["total_attempts"] for s in conv_stats.values())
            total_success = sum(s["successful"] for s in conv_stats.values())

            return {
                "uptime_seconds": uptime_seconds,
                "uptime_hours": uptime_seconds / 3600.0,
                "total_endpoints_tracked": len(self._endpoint_metrics),
                "total_providers_tracked": len(self._provider_conversions),
                "last_hour": {
                    "total_requests": total_ep_requests,
                    "total_errors": total_ep_errors,
                    "overall_error_rate": (total_ep_errors / total_ep_requests * 100.0) if total_ep_requests else 0.0,
                    "total_payment_attempts": total_attempts,
                    "total_successful_payments": total_success,
                    "overall_conversion_rate": (total_success / total_attempts * 100.0) if total_attempts else 0.0,
                },
            }

    # --------------------------------------------------------------------- #
    # Internos
    # --------------------------------------------------------------------- #

    def _window_ts(self, dt: datetime, window: TimeWindow) -> datetime:
        if window == TimeWindow.MINUTE:
            return dt.replace(second=0, microsecond=0)
        if window == TimeWindow.HOUR:
            return dt.replace(minute=0, second=0, microsecond=0)
        if window == TimeWindow.DAY:
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return dt

    def _tick_cleanup(self) -> None:
        self._ops += 1
        if self._ops >= self._cleanup_every:
            self._cleanup_old_data()
            self._ops = 0

    def _cleanup_old_data(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)

        # Endpoints
        for ep in list(self._endpoint_metrics.keys()):
            buckets = self._endpoint_metrics[ep]
            for ts in [ts for ts in buckets.keys() if ts < cutoff]:
                del buckets[ts]
            if not buckets:
                del self._endpoint_metrics[ep]

        # Proveedores
        for prov in list(self._provider_conversions.keys()):
            buckets = self._provider_conversions[prov]
            for ts in [ts for ts in buckets.keys() if ts < cutoff]:
                del buckets[ts]
            if not buckets:
                del self._provider_conversions[prov]

# Fin del archivo backend\app\modules\payments\metrics\aggregators\storage_core.py