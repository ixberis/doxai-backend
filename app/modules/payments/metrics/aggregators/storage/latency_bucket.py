
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/latency_bucket.py

Bucket de latencias para cálculo de percentiles y tasa de error.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

from .utils import percentile_linear_interp


@dataclass
class LatencyBucket:
    """
    Estructura de latencias y errores para un período.
    - Guarda una ventana acotada (maxlen) de latencias recientes.
    - Acumula conteos totales y por tipo de error.
    """
    latencies: Deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    total_requests: int = 0
    total_errors: int = 0
    error_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add_latency(self, latency_ms: float, error: Optional[str] = None) -> None:
        """Registra latencia y (opcionalmente) un tipo de error."""
        self.latencies.append(float(latency_ms))
        self.total_requests += 1
        if error:
            self.total_errors += 1
            self.error_by_type[str(error)] += 1

    def get_percentiles(self) -> Dict[str, float]:
        """Devuelve p50/p95/p99 y promedio (ms)."""
        if not self.latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}
        sorted_latencies = sorted(self.latencies)
        return {
            "p50": percentile_linear_interp(sorted_latencies, 0.50),
            "p95": percentile_linear_interp(sorted_latencies, 0.95),
            "p99": percentile_linear_interp(sorted_latencies, 0.99),
            "avg": statistics.mean(sorted_latencies),
        }

    def get_error_rate(self) -> float:
        """Porcentaje de errores respecto al total de solicitudes."""
        if self.total_requests == 0:
            return 0.0
        return (self.total_errors / self.total_requests) * 100.0
# Fin del archivo backend\app\modules\payments\metrics\aggregators\latency_bucket.py