
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/exporters/prometheus_exporter.py

Exporter Prometheus para el módulo de pagos.
Expone métricas en formato Prometheus y registra colectores personalizados.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Registro global de Prometheus
# --------------------------------------------------------------------------
registry = CollectorRegistry()

# --------------------------------------------------------------------------
# Definición de métricas
# --------------------------------------------------------------------------

# Totales de checkout
CHECKOUT_STARTED_TOTAL = Counter(
    "payments_checkout_started_total",
    "Número total de checkouts iniciados",
    ["provider", "currency"],
    registry=registry,
)

# Webhooks - BLOQUE C+: Métricas separadas (verified vs outcome)
WEBHOOKS_RECEIVED_TOTAL = Counter(
    "payments_webhook_received_total",
    "Total webhooks recibidos por proveedor",
    ["provider"],
    registry=registry,
)

# C+ HARDENING: Separar verificación de outcome
WEBHOOKS_VERIFIED_TOTAL = Counter(
    "payments_webhook_verified_total",
    "Total webhooks por resultado de verificación (success/failure)",
    ["provider", "result"],  # result: success/failure
    registry=registry,
)
WEBHOOKS_OUTCOME_TOTAL = Counter(
    "payments_webhook_outcome_total",
    "Total webhooks por outcome de negocio (success/ignored/duplicate/error)",
    ["provider", "outcome"],  # outcome: success/ignored/duplicate/error
    registry=registry,
)

WEBHOOKS_REJECTED_TOTAL = Counter(
    "payments_webhook_rejected_total",
    "Total webhooks rechazados por proveedor y razón",
    ["provider", "reason"],
    registry=registry,
)
WEBHOOKS_PROCESSING_SECONDS = Histogram(
    "payments_webhook_processing_seconds",
    "Tiempo de procesamiento de webhooks (segundos)",
    ["provider"],
    registry=registry,
)
AMOUNT_MISMATCH_TOTAL = Counter(
    "payments_amount_mismatch_total",
    "Total de mismatches de monto detectados",
    ["provider"],
    registry=registry,
)
CREDIT_APPLIED_TOTAL = Counter(
    "payments_credit_applied_total",
    "Total de créditos aplicados desde webhooks",
    ["provider"],
    registry=registry,
)

# Reembolsos
REFUND_REQUESTS_TOTAL = Counter(
    "payments_refund_requests_total",
    "Número total de solicitudes de reembolso",
    ["provider"],
    registry=registry,
)
REFUND_SUCCEEDED_TOTAL = Counter(
    "payments_refund_succeeded_total",
    "Número total de reembolsos exitosos",
    ["provider"],
    registry=registry,
)
REFUND_FAILED_TOTAL = Counter(
    "payments_refund_failed_total",
    "Número total de reembolsos fallidos",
    ["provider"],
    registry=registry,
)
REFUND_PROCESSING_SECONDS = Histogram(
    "payments_refund_processing_seconds",
    "Tiempo de procesamiento de reembolsos (segundos)",
    ["provider"],
    registry=registry,
)

# Estado de pagos
PAYMENTS_STATUS_TOTAL = Counter(
    "payments_status_total",
    "Pagos agrupados por estado",
    ["provider", "currency", "status"],
    registry=registry,
)

# Créditos (gauges)
CREDITS_TOTAL = Gauge(
    "credits_wallet_total",
    "Total de créditos en el sistema (estimado)",
    ["currency"],
    registry=registry,
)

# --------------------------------------------------------------------------
# Funciones auxiliares
# --------------------------------------------------------------------------
def render_prometheus_metrics() -> bytes:
    """
    Genera la salida actual de las métricas en formato Prometheus.
    """
    return generate_latest(registry)


def observe_webhook_received(provider: str):
    """Registra recepción de un webhook."""
    WEBHOOKS_RECEIVED_TOTAL.labels(provider=provider).inc()


def observe_webhook_verified(provider: str, verification_result: str, duration: float):
    """
    C+ HARDENING: Registra resultado de verificación del webhook.
    
    Args:
        provider: stripe/paypal
        verification_result: success/failure (solo verificación de firma)
        duration: Tiempo de procesamiento en segundos
    """
    WEBHOOKS_VERIFIED_TOTAL.labels(provider=provider, result=verification_result).inc()
    WEBHOOKS_PROCESSING_SECONDS.labels(provider=provider).observe(duration)
    logger.debug(f"[Prometheus] Webhook {provider} verified={verification_result} duration={duration:.4f}s")


def observe_webhook_outcome(provider: str, outcome: str):
    """
    C+ HARDENING: Registra outcome de negocio del webhook.
    
    Args:
        provider: stripe/paypal
        outcome: success/ignored/duplicate/error
    """
    WEBHOOKS_OUTCOME_TOTAL.labels(provider=provider, outcome=outcome).inc()
    logger.debug(f"[Prometheus] Webhook {provider} outcome={outcome}")


def observe_webhook_rejected(provider: str, reason: str):
    """
    Registra webhook rechazado.
    
    Args:
        provider: stripe/paypal
        reason: invalid_signature/rate_limited/processing_error
    """
    WEBHOOKS_REJECTED_TOTAL.labels(provider=provider, reason=reason).inc()
    logger.debug(f"[Prometheus] Webhook {provider} rejected reason={reason}")


def observe_amount_mismatch(provider: str):
    """Registra mismatch de monto."""
    AMOUNT_MISMATCH_TOTAL.labels(provider=provider).inc()
    logger.warning(f"[Prometheus] Amount mismatch detected for {provider}")


def observe_credit_applied(provider: str):
    """Registra crédito aplicado."""
    CREDIT_APPLIED_TOTAL.labels(provider=provider).inc()
    logger.debug(f"[Prometheus] Credit applied from {provider}")


def observe_refund(provider: str, success: bool, duration: float):
    """
    Registra un reembolso procesado.
    """
    REFUND_REQUESTS_TOTAL.labels(provider=provider).inc()
    if success:
        REFUND_SUCCEEDED_TOTAL.labels(provider=provider).inc()
    else:
        REFUND_FAILED_TOTAL.labels(provider=provider).inc()
    REFUND_PROCESSING_SECONDS.labels(provider=provider).observe(duration)
    logger.debug(f"[Prometheus] Refund {provider} success={success} duration={duration:.4f}s")


def increment_checkout(provider: str, currency: str):
    """Incrementa el contador de checkouts iniciados."""
    CHECKOUT_STARTED_TOTAL.labels(provider=provider, currency=currency).inc()
    logger.debug(f"[Prometheus] Checkout iniciado {provider}/{currency}")


def record_payment_status(provider: str, currency: str, status: str):
    """Incrementa el contador de pagos por estado."""
    PAYMENTS_STATUS_TOTAL.labels(provider=provider, currency=currency, status=status).inc()


def update_wallet_balance(currency: str, total_credits: float):
    """Actualiza el gauge con el total estimado de créditos."""
    CREDITS_TOTAL.labels(currency=currency).set(total_credits)
    logger.debug(f"[Prometheus] Créditos totales {currency}={total_credits}")


# --------------------------------------------------------------------------
# Health-check de Prometheus
# --------------------------------------------------------------------------
def prometheus_ping() -> dict:
    """Devuelve un simple dict para verificar salud del exporter."""
    return {
        "status": "ok",
        "service": "payments-metrics",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics_registered": len(registry._names_to_collectors),
    }

# Fin del archivo backend\app\modules\payments\metrics\exporters\prometheus_exporter.py