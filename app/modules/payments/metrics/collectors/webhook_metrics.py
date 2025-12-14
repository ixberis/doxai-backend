
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/collectors/webhook_metrics.py

Métricas específicas para webhooks de pagos (FASE 3).

Provee counters y histogramas para observabilidad de webhooks.

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

from __future__ import annotations

import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class WebhookMetrics:
    """Contenedor de métricas de webhooks."""
    
    # Counters
    received_total: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    verified_total: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    rejected_total: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    amount_mismatch_total: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    credit_applied_total: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Histograms (latencias en ms)
    processing_times: Dict[str, List[float]] = field(
        default_factory=lambda: defaultdict(list)
    )


class WebhookMetricsCollector:
    """
    Colector de métricas de webhooks.
    
    Singleton para uso global.
    """
    
    _instance: Optional["WebhookMetricsCollector"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._metrics = WebhookMetrics()
            cls._instance._initialized = True
        return cls._instance
    
    @property
    def metrics(self) -> WebhookMetrics:
        return self._metrics
    
    # ----------------------------- Counters ------------------------------ #
    
    def inc_received(self, provider: str) -> None:
        """Incrementa contador de webhooks recibidos."""
        self._metrics.received_total[provider.lower()] += 1
        logger.debug(f"webhook_received_total{{provider={provider}}} incremented")
    
    def inc_verified(self, provider: str, result: str = "success") -> None:
        """
        Incrementa contador de webhooks verificados.
        
        Args:
            provider: stripe/paypal
            result: success/failure
        """
        self._metrics.verified_total[provider.lower()][result.lower()] += 1
        logger.debug(f"webhook_verified_total{{provider={provider},result={result}}} incremented")
    
    def inc_rejected(self, provider: str, reason: str) -> None:
        """
        Incrementa contador de webhooks rechazados.
        
        Args:
            provider: stripe/paypal
            reason: invalid_signature/rate_limited/invalid_payload/etc
        """
        self._metrics.rejected_total[provider.lower()][reason.lower()] += 1
        logger.debug(f"webhook_rejected_total{{provider={provider},reason={reason}}} incremented")
    
    def inc_amount_mismatch(self, provider: str) -> None:
        """Incrementa contador de mismatches de monto."""
        self._metrics.amount_mismatch_total[provider.lower()] += 1
        logger.warning(f"payment_amount_mismatch_total{{provider={provider}}} incremented")
    
    def inc_credit_applied(self, provider: str) -> None:
        """Incrementa contador de créditos aplicados."""
        self._metrics.credit_applied_total[provider.lower()] += 1
        logger.debug(f"credit_applied_total{{provider={provider}}} incremented")
    
    # ----------------------------- Histograms ------------------------------ #
    
    def observe_processing_time(self, provider: str, duration_ms: float) -> None:
        """
        Registra tiempo de procesamiento de webhook.
        
        Args:
            provider: stripe/paypal
            duration_ms: Tiempo en milisegundos
        """
        self._metrics.processing_times[provider.lower()].append(duration_ms)
        
        # Mantener solo últimas 1000 mediciones por proveedor
        if len(self._metrics.processing_times[provider.lower()]) > 1000:
            self._metrics.processing_times[provider.lower()] = \
                self._metrics.processing_times[provider.lower()][-1000:]
        
        if duration_ms > 5000:
            logger.warning(f"Slow webhook processing for {provider}: {duration_ms:.2f}ms")
    
    @contextmanager
    def track_processing_time(self, provider: str):
        """
        Context manager para medir tiempo de procesamiento.
        
        Usage:
            with metrics.track_processing_time("stripe"):
                # process webhook
        """
        start_time = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - start_time) * 1000
            self.observe_processing_time(provider, duration_ms)
    
    # ----------------------------- Consultas ------------------------------ #
    
    def get_summary(self) -> Dict:
        """Obtiene resumen de todas las métricas."""
        m = self._metrics
        
        def calc_percentiles(values: List[float]) -> Dict:
            if not values:
                return {"p50": 0, "p95": 0, "p99": 0, "count": 0}
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            return {
                "p50": sorted_vals[int(n * 0.5)] if n > 0 else 0,
                "p95": sorted_vals[int(n * 0.95)] if n > 0 else 0,
                "p99": sorted_vals[int(n * 0.99)] if n > 0 else 0,
                "count": n,
            }
        
        return {
            "received_total": dict(m.received_total),
            "verified_total": {k: dict(v) for k, v in m.verified_total.items()},
            "rejected_total": {k: dict(v) for k, v in m.rejected_total.items()},
            "amount_mismatch_total": dict(m.amount_mismatch_total),
            "credit_applied_total": dict(m.credit_applied_total),
            "processing_times": {
                provider: calc_percentiles(times)
                for provider, times in m.processing_times.items()
            },
        }
    
    def get_prometheus_metrics(self) -> str:
        """
        Exporta métricas en formato Prometheus.
        
        Returns:
            String con métricas en formato Prometheus text exposition.
        """
        lines = []
        m = self._metrics
        
        # webhook_received_total
        lines.append("# HELP webhook_received_total Total webhooks received")
        lines.append("# TYPE webhook_received_total counter")
        for provider, count in m.received_total.items():
            lines.append(f'webhook_received_total{{provider="{provider}"}} {count}')
        
        # webhook_verified_total
        lines.append("# HELP webhook_verified_total Total webhooks verified")
        lines.append("# TYPE webhook_verified_total counter")
        for provider, results in m.verified_total.items():
            for result, count in results.items():
                lines.append(f'webhook_verified_total{{provider="{provider}",result="{result}"}} {count}')
        
        # webhook_rejected_total
        lines.append("# HELP webhook_rejected_total Total webhooks rejected")
        lines.append("# TYPE webhook_rejected_total counter")
        for provider, reasons in m.rejected_total.items():
            for reason, count in reasons.items():
                lines.append(f'webhook_rejected_total{{provider="{provider}",reason="{reason}"}} {count}')
        
        # payment_amount_mismatch_total
        lines.append("# HELP payment_amount_mismatch_total Total amount mismatches detected")
        lines.append("# TYPE payment_amount_mismatch_total counter")
        for provider, count in m.amount_mismatch_total.items():
            lines.append(f'payment_amount_mismatch_total{{provider="{provider}"}} {count}')
        
        # credit_applied_total
        lines.append("# HELP credit_applied_total Total credits applied from webhooks")
        lines.append("# TYPE credit_applied_total counter")
        for provider, count in m.credit_applied_total.items():
            lines.append(f'credit_applied_total{{provider="{provider}"}} {count}')
        
        return "\n".join(lines)
    
    def reset(self) -> None:
        """Resetea todas las métricas (útil para tests)."""
        self._metrics = WebhookMetrics()


# Singleton global
_webhook_metrics: Optional[WebhookMetricsCollector] = None


def get_webhook_metrics() -> WebhookMetricsCollector:
    """Obtiene la instancia global del colector de métricas de webhooks."""
    global _webhook_metrics
    if _webhook_metrics is None:
        _webhook_metrics = WebhookMetricsCollector()
    return _webhook_metrics


def reset_webhook_metrics() -> None:
    """Resetea las métricas de webhooks (útil para tests)."""
    global _webhook_metrics
    if _webhook_metrics:
        _webhook_metrics.reset()


__all__ = [
    "WebhookMetricsCollector",
    "WebhookMetrics",
    "get_webhook_metrics",
    "reset_webhook_metrics",
]

# Fin del archivo backend/app/modules/payments/metrics/collectors/webhook_metrics.py
