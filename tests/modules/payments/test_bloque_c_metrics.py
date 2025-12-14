# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/test_bloque_c_metrics.py

Tests para BLOQUE C+: Métricas integradas a Prometheus (verified vs outcome).

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from app.modules.payments.metrics.helpers import (
    map_webhook_result_to_metrics,
    get_verification_and_outcome,
    WebhookMetricResult,
    WebhookVerificationResult,
    WebhookOutcome,
    should_increment_verified,
    should_increment_rejected,
)


class TestMapWebhookResultToMetrics:
    """Tests para el helper de mapeo de resultados."""

    def test_ok_status_maps_to_success(self):
        """status=ok mapea a SUCCESS."""
        result = {"status": "ok", "event": "payment_succeeded", "payment_id": 123}
        metric, desc = map_webhook_result_to_metrics(result)
        
        assert metric == WebhookMetricResult.SUCCESS
        assert desc == "payment_succeeded"

    def test_ok_status_with_refund_event(self):
        """status=ok con evento de refund."""
        result = {"status": "ok", "event": "refund_processed", "refund_id": 456}
        metric, desc = map_webhook_result_to_metrics(result)
        
        assert metric == WebhookMetricResult.SUCCESS
        assert desc == "refund_processed"

    def test_duplicate_status_maps_to_duplicate(self):
        """status=duplicate mapea a DUPLICATE."""
        result = {"status": "duplicate", "event_id": "evt_1234567890abcdef"}
        metric, desc = map_webhook_result_to_metrics(result)
        
        assert metric == WebhookMetricResult.DUPLICATE
        assert "duplicate:" in desc
        assert "evt_1234" in desc  # Primeros 8 caracteres del event_id

    def test_ignored_status_maps_to_ignored(self):
        """status=ignored mapea a IGNORED."""
        result = {"status": "ignored", "reason": "payment_id not found"}
        metric, desc = map_webhook_result_to_metrics(result)
        
        assert metric == WebhookMetricResult.IGNORED
        assert desc == "payment_id not found"

    def test_ignored_with_message_fallback(self):
        """status=ignored usa message si no hay reason."""
        result = {"status": "ignored", "message": "Event type does not require action"}
        metric, desc = map_webhook_result_to_metrics(result)
        
        assert metric == WebhookMetricResult.IGNORED
        assert desc == "Event type does not require action"

    def test_unknown_status_maps_to_error(self):
        """status desconocido mapea a ERROR."""
        result = {"status": "weird_status"}
        metric, desc = map_webhook_result_to_metrics(result)
        
        assert metric == WebhookMetricResult.ERROR
        assert "unknown_status" in desc

    def test_missing_status_maps_to_error(self):
        """Sin status mapea a ERROR."""
        result = {"event": "something"}
        metric, desc = map_webhook_result_to_metrics(result)
        
        assert metric == WebhookMetricResult.ERROR


class TestGetVerificationAndOutcome:
    """C+ HARDENING: Tests para separación de verified vs outcome."""

    def test_ok_gives_verified_success_and_outcome_success(self):
        """ok → verified success + outcome success."""
        metric_result = WebhookMetricResult.SUCCESS
        verification, outcome = get_verification_and_outcome(metric_result)
        
        assert verification == WebhookVerificationResult.SUCCESS
        assert outcome == WebhookOutcome.SUCCESS

    def test_ignored_gives_verified_success_and_outcome_ignored(self):
        """ignored → verified success + outcome ignored."""
        metric_result = WebhookMetricResult.IGNORED
        verification, outcome = get_verification_and_outcome(metric_result)
        
        assert verification == WebhookVerificationResult.SUCCESS
        assert outcome == WebhookOutcome.IGNORED

    def test_duplicate_gives_verified_success_and_outcome_duplicate(self):
        """duplicate → verified success + outcome duplicate."""
        metric_result = WebhookMetricResult.DUPLICATE
        verification, outcome = get_verification_and_outcome(metric_result)
        
        assert verification == WebhookVerificationResult.SUCCESS
        assert outcome == WebhookOutcome.DUPLICATE

    def test_error_gives_verified_failure_and_outcome_error(self):
        """error → verified failure + outcome error."""
        metric_result = WebhookMetricResult.ERROR
        verification, outcome = get_verification_and_outcome(metric_result)
        
        assert verification == WebhookVerificationResult.FAILURE
        assert outcome == WebhookOutcome.ERROR


class TestShouldIncrementHelpers:
    """Tests para helpers de decisión de incremento."""

    def test_success_should_increment_verified(self):
        """SUCCESS debe incrementar verified."""
        assert should_increment_verified(WebhookMetricResult.SUCCESS) is True

    def test_duplicate_should_increment_verified(self):
        """DUPLICATE debe incrementar verified (idempotencia ok)."""
        assert should_increment_verified(WebhookMetricResult.DUPLICATE) is True

    def test_ignored_should_increment_verified(self):
        """C+ FIX: IGNORED ahora incrementa verified (payload válido)."""
        assert should_increment_verified(WebhookMetricResult.IGNORED) is True

    def test_error_should_not_increment_verified(self):
        """ERROR no debe incrementar verified."""
        assert should_increment_verified(WebhookMetricResult.ERROR) is False

    def test_error_should_increment_rejected(self):
        """ERROR debe incrementar rejected."""
        assert should_increment_rejected(WebhookMetricResult.ERROR) is True

    def test_success_should_not_increment_rejected(self):
        """SUCCESS no debe incrementar rejected."""
        assert should_increment_rejected(WebhookMetricResult.SUCCESS) is False


class TestPrometheusExporterFunctions:
    """Tests para funciones del exporter Prometheus."""

    def test_observe_webhook_received_increments_counter(self):
        """observe_webhook_received incrementa contador."""
        from app.modules.payments.metrics.exporters.prometheus_exporter import (
            observe_webhook_received,
            WEBHOOKS_RECEIVED_TOTAL,
        )
        
        # Obtener valor actual
        before = WEBHOOKS_RECEIVED_TOTAL.labels(provider="test_stripe")._value.get()
        
        observe_webhook_received("test_stripe")
        
        after = WEBHOOKS_RECEIVED_TOTAL.labels(provider="test_stripe")._value.get()
        assert after == before + 1

    def test_observe_webhook_verified_increments_counter(self):
        """observe_webhook_verified incrementa contador."""
        from app.modules.payments.metrics.exporters.prometheus_exporter import (
            observe_webhook_verified,
            WEBHOOKS_VERIFIED_TOTAL,
        )
        
        before = WEBHOOKS_VERIFIED_TOTAL.labels(
            provider="test_stripe", result="success"
        )._value.get()
        
        observe_webhook_verified("test_stripe", "success", 0.1)
        
        after = WEBHOOKS_VERIFIED_TOTAL.labels(
            provider="test_stripe", result="success"
        )._value.get()
        assert after == before + 1

    def test_observe_webhook_outcome_increments_counter(self):
        """C+ HARDENING: observe_webhook_outcome incrementa contador."""
        from app.modules.payments.metrics.exporters.prometheus_exporter import (
            observe_webhook_outcome,
            WEBHOOKS_OUTCOME_TOTAL,
        )
        
        before = WEBHOOKS_OUTCOME_TOTAL.labels(
            provider="test_stripe", outcome="success"
        )._value.get()
        
        observe_webhook_outcome("test_stripe", "success")
        
        after = WEBHOOKS_OUTCOME_TOTAL.labels(
            provider="test_stripe", outcome="success"
        )._value.get()
        assert after == before + 1

    def test_observe_webhook_outcome_ignored(self):
        """C+ HARDENING: observe_webhook_outcome con ignored."""
        from app.modules.payments.metrics.exporters.prometheus_exporter import (
            observe_webhook_outcome,
            WEBHOOKS_OUTCOME_TOTAL,
        )
        
        before = WEBHOOKS_OUTCOME_TOTAL.labels(
            provider="test_paypal", outcome="ignored"
        )._value.get()
        
        observe_webhook_outcome("test_paypal", "ignored")
        
        after = WEBHOOKS_OUTCOME_TOTAL.labels(
            provider="test_paypal", outcome="ignored"
        )._value.get()
        assert after == before + 1

    def test_observe_webhook_rejected_increments_counter(self):
        """observe_webhook_rejected incrementa contador."""
        from app.modules.payments.metrics.exporters.prometheus_exporter import (
            observe_webhook_rejected,
            WEBHOOKS_REJECTED_TOTAL,
        )
        
        before = WEBHOOKS_REJECTED_TOTAL.labels(
            provider="test_stripe", reason="invalid_signature"
        )._value.get()
        
        observe_webhook_rejected("test_stripe", "invalid_signature")
        
        after = WEBHOOKS_REJECTED_TOTAL.labels(
            provider="test_stripe", reason="invalid_signature"
        )._value.get()
        assert after == before + 1

    def test_render_prometheus_metrics_returns_bytes(self):
        """render_prometheus_metrics retorna bytes."""
        from app.modules.payments.metrics.exporters.prometheus_exporter import (
            render_prometheus_metrics,
        )
        
        output = render_prometheus_metrics()
        assert isinstance(output, bytes)
        assert b"payments_webhook" in output or b"TYPE" in output
