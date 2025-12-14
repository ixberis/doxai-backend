# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/helpers/__init__.py

BLOQUE C+: Helper para mapear resultados de webhook a métricas.

Separa métricas de verificación (verified) vs outcome (resultado de negocio).

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

from typing import Any, Dict, Tuple
from enum import Enum


class WebhookMetricResult(str, Enum):
    """Resultados posibles para métricas de webhooks."""
    SUCCESS = "success"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"
    ERROR = "error"


class WebhookVerificationResult(str, Enum):
    """Resultados de verificación de firma del webhook."""
    SUCCESS = "success"
    FAILURE = "failure"


class WebhookOutcome(str, Enum):
    """Outcomes de negocio del webhook (post-verificación)."""
    SUCCESS = "success"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"
    ERROR = "error"


def map_webhook_result_to_metrics(result: Dict[str, Any]) -> Tuple[WebhookMetricResult, str]:
    """
    Mapea el resultado del handle_webhook a valores de métricas.
    
    El handler puede devolver:
    - {"status": "ok", "event": "payment_succeeded", ...}
    - {"status": "ignored", "reason": "...", ...}
    - {"status": "duplicate", "event_id": "...", ...}
    
    Args:
        result: Dict retornado por handle_webhook
    
    Returns:
        Tuple de (WebhookMetricResult, descripción)
    """
    status = result.get("status", "unknown")
    
    if status == "ok":
        event = result.get("event", "unknown")
        return WebhookMetricResult.SUCCESS, event
    
    if status == "duplicate":
        event_id = result.get("event_id", "unknown")
        return WebhookMetricResult.DUPLICATE, f"duplicate:{event_id[:8]}"
    
    if status == "ignored":
        reason = result.get("reason", result.get("message", "unknown"))
        return WebhookMetricResult.IGNORED, reason
    
    # Cualquier otro status se considera error
    return WebhookMetricResult.ERROR, f"unknown_status:{status}"


def get_verification_and_outcome(
    metric_result: WebhookMetricResult,
) -> Tuple[WebhookVerificationResult, WebhookOutcome]:
    """
    C+ HARDENING: Separa verification result del business outcome.
    
    Lógica:
    - SUCCESS → verificación OK, outcome success
    - IGNORED → verificación OK (payload válido), outcome ignored
    - DUPLICATE → verificación OK (idempotencia), outcome duplicate
    - ERROR → verificación FAILURE, outcome error
    
    Args:
        metric_result: Resultado del mapeo de webhook
    
    Returns:
        Tuple de (WebhookVerificationResult, WebhookOutcome)
    """
    if metric_result == WebhookMetricResult.SUCCESS:
        return WebhookVerificationResult.SUCCESS, WebhookOutcome.SUCCESS
    
    if metric_result == WebhookMetricResult.IGNORED:
        # Ignored significa que se verificó correctamente pero no requiere acción
        return WebhookVerificationResult.SUCCESS, WebhookOutcome.IGNORED
    
    if metric_result == WebhookMetricResult.DUPLICATE:
        # Duplicate significa que se verificó correctamente (idempotencia ok)
        return WebhookVerificationResult.SUCCESS, WebhookOutcome.DUPLICATE
    
    # ERROR = fallo de verificación o procesamiento
    return WebhookVerificationResult.FAILURE, WebhookOutcome.ERROR


def should_increment_verified(metric_result: WebhookMetricResult) -> bool:
    """
    Determina si se debe incrementar webhook_verified_total con success.
    
    C+ HARDENING: Ahora solo SUCCESS, IGNORED y DUPLICATE incrementan verified=success.
    ERROR incrementa verified=failure.
    """
    return metric_result in (
        WebhookMetricResult.SUCCESS,
        WebhookMetricResult.IGNORED,
        WebhookMetricResult.DUPLICATE,
    )


def should_increment_rejected(metric_result: WebhookMetricResult) -> bool:
    """Determina si se debe incrementar webhook_rejected_total."""
    return metric_result == WebhookMetricResult.ERROR


__all__ = [
    "WebhookMetricResult",
    "WebhookVerificationResult",
    "WebhookOutcome",
    "map_webhook_result_to_metrics",
    "get_verification_and_outcome",
    "should_increment_verified",
    "should_increment_rejected",
]
