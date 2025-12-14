
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/metrics_storage.py

Almacenamiento en memoria de métricas con agregación temporal.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Dict, List, Optional, Tuple
from enum import Enum


class TimeWindow(str, Enum):
    """Ventanas de tiempo para agregación."""
    MINUTE = "1m"
    HOUR = "1h"
    DAY = "1d"


@dataclass
class LatencyBucket:
    """Bucket de latencias para cálculo de percentiles."""
    latencies: deque = field(default_factory=lambda: deque(maxlen=1000))
    total_requests: int = 0
    total_errors: int = 0
    error_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add_latency(self, latency_ms: float, error: Optional[str] = None) -> None:
        """Agrega una latencia al bucket."""
        self.latencies.append(latency_ms)
        self.total_requests += 1
        if error:
            self.total_errors += 1
            self.error_by_type[error] += 1

    def get_percentiles(self) -> Dict[str, float]:
        """Calcula percentiles de latencia."""
        if not self.latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}

        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)

        def percentile(data: list, p: float) -> float:
            """Calcula percentil usando interpolación lineal."""
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            d0 = data[f]
            d1 = data[c]
            return d0 + (d1 - d0) * (k - f)

        return {
            "p50": percentile(sorted_latencies, 0.50),
            "p95": percentile(sorted_latencies, 0.95),
            "p99": percentile(sorted_latencies, 0.99),
            "avg": statistics.mean(sorted_latencies),
        }

    def get_error_rate(self) -> float:
        """Calcula la tasa de error."""
        if self.total_requests == 0:
            return 0.0
        return (self.total_errors / self.total_requests) * 100


@dataclass
class ConversionBucket:
    """Bucket de conversiones para un proveedor."""
    total_attempts: int = 0
    successful: int = 0
    failed: int = 0
    pending: int = 0
    cancelled: int = 0

    def record_attempt(self, status: str) -> None:
        """Registra un intento de pago con su estado."""
        self.total_attempts += 1

        status_lower = status.lower()
        if status_lower in ["paid", "completed", "succeeded"]:
            self.successful += 1
        elif status_lower in ["failed", "error", "rejected"]:
            self.failed += 1
        elif status_lower in ["pending", "created", "processing"]:
            self.pending += 1
        elif status_lower in ["cancelled", "canceled", "expired"]:
            self.cancelled += 1

    def get_conversion_rate(self) -> float:
        """Calcula la tasa de conversión (exitosos / intentos)."""
        if self.total_attempts == 0:
            return 0.0
        return (self.successful / self.total_attempts) * 100

    def get_failure_rate(self) -> float:
        """Calcula la tasa de fallo."""
        if self.total_attempts == 0:
            return 0.0
        return (self.failed / self.total_attempts) * 100


class MetricsStorage:
    """
    Almacenamiento thread-safe de métricas en memoria.
    Mantiene buckets por endpoint y proveedor con ventanas temporales.
    """

    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        self._lock = Lock()

        # Métricas por endpoint: endpoint -> timestamp -> LatencyBucket
        self._endpoint_metrics: Dict[str, Dict[datetime, LatencyBucket]] = defaultdict(
            lambda: defaultdict(LatencyBucket)
        )

        # Conversiones por proveedor: provider -> timestamp -> ConversionBucket
        self._provider_conversions: Dict[str, Dict[datetime, ConversionBucket]] = defaultdict(
            lambda: defaultdict(ConversionBucket)
        )

        # Metadata adicional
        self._start_time = datetime.now(timezone.utc)

        # Contador para limpieza periódica (cada N operaciones)
        self._operation_count = 0
        self._cleanup_threshold = 100  # Limpiar cada 100 operaciones

    def record_endpoint_call(
        self,
        endpoint: str,
        latency_ms: float,
        error: Optional[str] = None,
        window: TimeWindow = TimeWindow.MINUTE,
    ) -> None:
        """Registra una llamada a un endpoint."""
        with self._lock:
            timestamp = self._get_window_timestamp(datetime.now(timezone.utc), window)
            self._endpoint_metrics[endpoint][timestamp].add_latency(latency_ms, error)
            self._operation_count += 1

            # Limpieza periódica en lugar de en cada operación
            if self._operation_count >= self._cleanup_threshold:
                self._cleanup_old_data()
                self._operation_count = 0

    def record_payment_attempt(
        self,
        provider: str,
        status: str,
        window: TimeWindow = TimeWindow.MINUTE,
    ) -> None:
        """Registra un intento de pago."""
        with self._lock:
            timestamp = self._get_window_timestamp(datetime.now(timezone.utc), window)
            self._provider_conversions[provider][timestamp].record_attempt(status)
            self._operation_count += 1

            # Limpieza periódica en lugar de en cada operación
            if self._operation_count >= self._cleanup_threshold:
                self._cleanup_old_data()
                self._operation_count = 0

    def get_endpoint_metrics(
        self,
        endpoint: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Dict]:
        """Obtiene métricas agregadas por endpoint."""
        with self._lock:
            return self._get_endpoint_metrics_unlocked(endpoint, since)

    def _get_endpoint_metrics_unlocked(
        self,
        endpoint: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Dict]:
        """Versión sin lock para uso interno."""
        since = since or (datetime.now(timezone.utc) - timedelta(hours=1))

        if endpoint:
            endpoints_to_process = {endpoint: self._endpoint_metrics.get(endpoint, {})}
        else:
            endpoints_to_process = self._endpoint_metrics

        result = {}
        for ep, buckets in endpoints_to_process.items():
            filtered_buckets = [
                bucket for ts, bucket in buckets.items() if ts >= since
            ]

            if not filtered_buckets:
                continue

            # Agregar todos los buckets
            all_latencies = []
            total_requests = 0
            total_errors = 0
            error_types = defaultdict(int)

            for bucket in filtered_buckets:
                all_latencies.extend(bucket.latencies)
                total_requests += bucket.total_requests
                total_errors += bucket.total_errors
                for err_type, count in bucket.error_by_type.items():
                    error_types[err_type] += count

                # Calcular percentiles agregados
                percentiles = {}
                if all_latencies:
                    sorted_latencies = sorted(all_latencies)

                    def percentile(data: list, p: float) -> float:
                        """Calcula percentil usando interpolación lineal."""
                        if not data:
                            return 0.0
                        k = (len(data) - 1) * p
                        f = int(k)
                        c = f + 1
                        if c >= len(data):
                            return data[-1]
                        d0 = data[f]
                        d1 = data[c]
                        return d0 + (d1 - d0) * (k - f)

                    percentiles = {
                        "p50": percentile(sorted_latencies, 0.50),
                        "p95": percentile(sorted_latencies, 0.95),
                        "p99": percentile(sorted_latencies, 0.99),
                        "avg": statistics.mean(sorted_latencies),
                    }

            result[ep] = {
                "total_requests": total_requests,
                "total_errors": total_errors,
                "error_rate": (total_errors / total_requests * 100) if total_requests > 0 else 0.0,
                "latency": percentiles,
                "errors_by_type": dict(error_types),
            }

        return result

    def get_provider_conversions(
        self,
        provider: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Dict]:
        """Obtiene métricas de conversión por proveedor."""
        with self._lock:
            return self._get_provider_conversions_unlocked(provider, since)

    def _get_provider_conversions_unlocked(
        self,
        provider: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> Dict[str, Dict]:
        """Versión sin lock para uso interno."""
        since = since or (datetime.now(timezone.utc) - timedelta(hours=1))

        if provider:
            providers_to_process = {provider: self._provider_conversions.get(provider, {})}
        else:
            providers_to_process = self._provider_conversions

        result = {}
        for prov, buckets in providers_to_process.items():
            filtered_buckets = [
                bucket for ts, bucket in buckets.items() if ts >= since
            ]

            if not filtered_buckets:
                continue

            # Agregar todos los buckets
            total_attempts = sum(b.total_attempts for b in filtered_buckets)
            successful = sum(b.successful for b in filtered_buckets)
            failed = sum(b.failed for b in filtered_buckets)
            pending = sum(b.pending for b in filtered_buckets)
            cancelled = sum(b.cancelled for b in filtered_buckets)

            result[prov] = {
                "total_attempts": total_attempts,
                "successful": successful,
                "failed": failed,
                "pending": pending,
                "cancelled": cancelled,
                "conversion_rate": (successful / total_attempts * 100) if total_attempts > 0 else 0.0,
                "failure_rate": (failed / total_attempts * 100) if total_attempts > 0 else 0.0,
            }

        return result

    def get_summary(self) -> Dict:
        """Obtiene un resumen general de todas las métricas."""
        with self._lock:
            now = datetime.now(timezone.utc)
            uptime_seconds = (now - self._start_time).total_seconds()

            # Métricas de endpoints (última hora) - usar versión sin lock
            since_one_hour = now - timedelta(hours=1)
            endpoint_stats = self._get_endpoint_metrics_unlocked(since=since_one_hour)
            total_endpoint_requests = sum(
                stats["total_requests"] for stats in endpoint_stats.values()
            )
            total_endpoint_errors = sum(
                stats["total_errors"] for stats in endpoint_stats.values()
            )

            # Métricas de conversión (última hora) - usar versión sin lock
            conversion_stats = self._get_provider_conversions_unlocked(since=since_one_hour)
            total_payment_attempts = sum(
                stats["total_attempts"] for stats in conversion_stats.values()
            )
            total_successful = sum(
                stats["successful"] for stats in conversion_stats.values()
            )

            return {
                "uptime_seconds": uptime_seconds,
                "uptime_hours": uptime_seconds / 3600,
                "total_endpoints_tracked": len(self._endpoint_metrics),
                "total_providers_tracked": len(self._provider_conversions),
                "last_hour": {
                    "total_requests": total_endpoint_requests,
                    "total_errors": total_endpoint_errors,
                    "overall_error_rate": (
                        total_endpoint_errors / total_endpoint_requests * 100
                    ) if total_endpoint_requests > 0 else 0.0,
                    "total_payment_attempts": total_payment_attempts,
                    "total_successful_payments": total_successful,
                    "overall_conversion_rate": (
                        total_successful / total_payment_attempts * 100
                    ) if total_payment_attempts > 0 else 0.0,
                },
            }

    def _get_window_timestamp(self, dt: datetime, window: TimeWindow) -> datetime:
        """Redondea un timestamp a la ventana temporal especificada."""
        if window == TimeWindow.MINUTE:
            return dt.replace(second=0, microsecond=0)
        elif window == TimeWindow.HOUR:
            return dt.replace(minute=0, second=0, microsecond=0)
        elif window == TimeWindow.DAY:
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return dt

    def _cleanup_old_data(self) -> None:
        """Limpia datos antiguos basándose en el período de retención."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)

        # Limpiar métricas de endpoints
        for endpoint in list(self._endpoint_metrics.keys()):
            buckets = self._endpoint_metrics[endpoint]
            old_timestamps = [ts for ts in buckets.keys() if ts < cutoff]
            for ts in old_timestamps:
                del buckets[ts]

            # Eliminar endpoint si no tiene datos
            if not buckets:
                del self._endpoint_metrics[endpoint]

        # Limpiar conversiones de proveedores
        for provider in list(self._provider_conversions.keys()):
            buckets = self._provider_conversions[provider]
            old_timestamps = [ts for ts in buckets.keys() if ts < cutoff]
            for ts in old_timestamps:
                del buckets[ts]

            # Eliminar proveedor si no tiene datos
            if not buckets:
                del self._provider_conversions[provider]
# Fin del archivo backend\app\modules\payments\metrics\aggregators\metrics_storage.py
