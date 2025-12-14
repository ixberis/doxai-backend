
# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/test_phase3_hardening.py

Tests para FASE 3: Rate Limiting, Métricas y Sanitización de webhooks.

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

from app.modules.payments.middleware.rate_limiter import (
    SlidingWindowRateLimiter,
    reset_rate_limiter,
    get_webhook_rate_limiter,
    check_webhook_rate_limit,
)
from app.modules.payments.services.webhooks.payload_sanitizer import (
    sanitize_webhook_payload,
    extract_audit_fields,
    compute_payload_hash,
    PII_FIELDS,
)
from app.modules.payments.metrics.collectors.webhook_metrics import (
    get_webhook_metrics,
    reset_webhook_metrics,
)


# ============================================================================
# Tests para Rate Limiting (3.1)
# ============================================================================

class TestSlidingWindowRateLimiter:
    """Tests para el rate limiter de ventana deslizante."""

    def test_allows_requests_under_limit(self):
        """Permite requests bajo el límite."""
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=1)
        
        for i in range(5):
            is_allowed, remaining = limiter.is_allowed("192.168.1.1")
            assert is_allowed is True
            assert remaining == 5 - i - 1

    def test_blocks_requests_over_limit(self):
        """Bloquea requests sobre el límite."""
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=1)
        
        # Primeras 3 requests pasan
        for _ in range(3):
            is_allowed, _ = limiter.is_allowed("192.168.1.1")
            assert is_allowed is True
        
        # La 4ta request es bloqueada
        is_allowed, remaining = limiter.is_allowed("192.168.1.1")
        assert is_allowed is False
        assert remaining == 0

    def test_different_ips_have_separate_limits(self):
        """IPs diferentes tienen límites separados."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=1)
        
        # IP 1 puede hacer 2 requests
        limiter.is_allowed("192.168.1.1")
        limiter.is_allowed("192.168.1.1")
        is_allowed, _ = limiter.is_allowed("192.168.1.1")
        assert is_allowed is False
        
        # IP 2 aún puede hacer requests
        is_allowed, _ = limiter.is_allowed("192.168.1.2")
        assert is_allowed is True

    def test_retry_after_calculation(self):
        """Calcula correctamente el tiempo de retry."""
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=5)
        
        limiter.is_allowed("192.168.1.1")
        retry_after = limiter.get_retry_after("192.168.1.1")
        
        # Debe ser aproximadamente 5 segundos
        assert 4 <= retry_after <= 6

    def test_reset_clears_all_records(self):
        """Reset limpia todos los registros."""
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=1)
        
        limiter.is_allowed("192.168.1.1")
        is_allowed, _ = limiter.is_allowed("192.168.1.1")
        assert is_allowed is False
        
        limiter.reset()
        
        is_allowed, _ = limiter.is_allowed("192.168.1.1")
        assert is_allowed is True


class TestRateLimitDependency:
    """Tests de integración ligera para rate limiting (comportamiento 11→429)."""

    def test_rate_limit_11_requests_blocked_in_production(self):
        """11 requests rápidas superan el límite y la última se bloquea."""
        # Simula entorno no-dev (producción) usando el rate limiter directamente
        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)

        # Primeras 10 requests pasan
        for i in range(10):
            is_allowed, remaining = limiter.is_allowed("203.0.113.1")
            assert is_allowed is True, f"Request {i+1} debería pasar"
            assert remaining == 10 - i - 1

        # La request 11 se bloquea
        is_allowed, remaining = limiter.is_allowed("203.0.113.1")
        assert is_allowed is False
        assert remaining == 0

    def test_rate_limit_separate_ip_buckets(self):
        """IPs distintas tienen buckets de rate limit independientes."""
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)

        # IP A llena su bucket
        for _ in range(5):
            is_allowed, _ = limiter.is_allowed("198.51.100.10")
            assert is_allowed is True

        is_allowed, _ = limiter.is_allowed("198.51.100.10")
        assert is_allowed is False

        # IP B aún puede usar sus 5 requests
        for i in range(5):
            is_allowed, remaining = limiter.is_allowed("198.51.100.20")
            assert is_allowed is True
            assert remaining == 5 - i - 1


# ============================================================================
# Tests para Sanitización de Payloads (3.3)
# ============================================================================

class TestPayloadSanitization:
    """Tests para sanitización de payloads de webhooks."""

    def test_removes_email_from_payload(self):
        """Elimina email del payload."""
        payload = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "email": "user@example.com",
            "customer_email": "customer@example.com",
            "data": {
                "email": "nested@example.com",
            }
        }
        
        sanitized = sanitize_webhook_payload("stripe", payload)
        
        assert "email" not in sanitized
        assert "customer_email" not in sanitized
        assert "email" not in sanitized.get("data", {})

    def test_removes_name_from_payload(self):
        """Elimina nombre del payload."""
        payload = {
            "id": "evt_123",
            "name": "John Doe",
            "first_name": "John",
            "last_name": "Doe",
            "customer_details": {
                "name": "Jane Doe",
            }
        }
        
        sanitized = sanitize_webhook_payload("stripe", payload)
        
        assert "name" not in sanitized
        assert "first_name" not in sanitized
        assert "last_name" not in sanitized

    def test_removes_address_from_payload(self):
        """Elimina dirección del payload."""
        payload = {
            "id": "evt_123",
            "address": "123 Main St",
            "shipping": {"line1": "456 Oak Ave"},
            "billing": {"city": "New York"},
        }
        
        sanitized = sanitize_webhook_payload("stripe", payload)
        
        assert "address" not in sanitized
        assert "shipping" not in sanitized
        assert "billing" not in sanitized

    def test_removes_phone_from_payload(self):
        """Elimina teléfono del payload."""
        payload = {
            "id": "evt_123",
            "phone": "+1234567890",
            "phone_number": "+0987654321",
        }
        
        sanitized = sanitize_webhook_payload("stripe", payload)
        
        assert "phone" not in sanitized
        assert "phone_number" not in sanitized

    def test_preserves_ids_and_amounts(self):
        """Preserva IDs y montos necesarios para auditoría."""
        payload = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "amount": 5000,
            "currency": "usd",
            "status": "complete",
            "payment_intent": "pi_123",
            "email": "user@example.com",  # Este debe eliminarse
        }
        
        sanitized = sanitize_webhook_payload("stripe", payload)
        
        assert sanitized["id"] == "evt_123"
        assert sanitized["type"] == "checkout.session.completed"
        assert sanitized["amount"] == 5000
        assert sanitized["currency"] == "usd"
        assert sanitized["status"] == "complete"
        assert sanitized["payment_intent"] == "pi_123"
        assert "email" not in sanitized

    def test_adds_sanitization_metadata(self):
        """Agrega metadatos de sanitización."""
        payload = {"id": "evt_123"}
        
        sanitized = sanitize_webhook_payload("stripe", payload)
        
        assert sanitized["__sanitized__"] is True
        assert sanitized["__provider__"] == "stripe"
        assert "__payload_hash__" in sanitized

    def test_removes_payer_info_paypal(self):
        """Elimina info del pagador de PayPal."""
        payload = {
            "id": "WH-123",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "payer": {
                "email_address": "buyer@example.com",
                "name": {"given_name": "John"},
            },
            "payer_info": {"email": "payer@example.com"},
        }
        
        sanitized = sanitize_webhook_payload("paypal", payload)
        
        assert "payer" not in sanitized
        assert "payer_info" not in sanitized

    def test_sanitizes_nested_structures(self):
        """Sanitiza estructuras anidadas."""
        payload = {
            "id": "evt_123",
            "data": {
                "object": {
                    "id": "cs_123",
                    "customer_email": "user@example.com",
                    "amount_total": 5000,
                    "customer_details": {
                        "email": "nested@example.com",
                        "name": "John",
                    }
                }
            }
        }
        
        sanitized = sanitize_webhook_payload("stripe", payload)
        
        # IDs y montos preservados vía core fields
        assert sanitized.get("core.event_id") == "evt_123"
        assert sanitized.get("core.provider_session_id") == "cs_123" or sanitized.get("core.provider_payment_id") == "cs_123"
        assert sanitized.get("core.amount") == 5000
        
        # PII eliminado
        result_str = str(sanitized)
        assert "user@example.com" not in result_str
        assert "nested@example.com" not in result_str
        assert "customer_details" not in result_str


class TestPayloadHash:
    """Tests para hash de payload."""

    def test_compute_hash_from_dict(self):
        """Computa hash desde diccionario."""
        payload = {"id": "test", "amount": 100}
        hash1 = compute_payload_hash(payload)
        hash2 = compute_payload_hash(payload)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex

    def test_compute_hash_from_bytes(self):
        """Computa hash desde bytes."""
        payload = b'{"id": "test"}'
        hash_val = compute_payload_hash(payload)
        
        assert len(hash_val) == 64

    def test_different_payloads_different_hashes(self):
        """Payloads diferentes producen hashes diferentes."""
        hash1 = compute_payload_hash({"id": "1"})
        hash2 = compute_payload_hash({"id": "2"})
        
        assert hash1 != hash2


class TestExtractAuditFields:
    """Tests para extracción de campos de auditoría."""

    def test_extracts_only_allowed_fields(self):
        """Extrae solo campos permitidos."""
        payload = {
            "id": "evt_123",
            "type": "checkout.completed",
            "amount": 5000,
            "email": "user@example.com",  # No permitido
            "name": "John",  # No permitido
        }
        
        audit = extract_audit_fields("stripe", payload)
        
        assert audit["id"] == "evt_123"
        assert audit["type"] == "checkout.completed"
        assert audit["amount"] == 5000
        assert "email" not in audit
        assert "name" not in audit


# ============================================================================
# Tests para Métricas de Webhooks (3.2)
# ============================================================================

class TestWebhookMetrics:
    """Tests para métricas de webhooks."""

    def setup_method(self):
        """Reset métricas antes de cada test."""
        reset_webhook_metrics()

    def test_increment_received_counter(self):
        """Incrementa contador de webhooks recibidos."""
        metrics = get_webhook_metrics()
        
        metrics.inc_received("stripe")
        metrics.inc_received("stripe")
        metrics.inc_received("paypal")
        
        summary = metrics.get_summary()
        assert summary["received_total"]["stripe"] == 2
        assert summary["received_total"]["paypal"] == 1

    def test_increment_verified_counter(self):
        """Incrementa contador de webhooks verificados."""
        metrics = get_webhook_metrics()
        
        metrics.inc_verified("stripe", "success")
        metrics.inc_verified("stripe", "success")
        metrics.inc_verified("stripe", "failure")
        
        summary = metrics.get_summary()
        assert summary["verified_total"]["stripe"]["success"] == 2
        assert summary["verified_total"]["stripe"]["failure"] == 1

    def test_increment_rejected_counter(self):
        """Incrementa contador de webhooks rechazados."""
        metrics = get_webhook_metrics()
        
        metrics.inc_rejected("stripe", "invalid_signature")
        metrics.inc_rejected("stripe", "rate_limited")
        
        summary = metrics.get_summary()
        assert summary["rejected_total"]["stripe"]["invalid_signature"] == 1
        assert summary["rejected_total"]["stripe"]["rate_limited"] == 1

    def test_increment_amount_mismatch_counter(self):
        """Incrementa contador de mismatches de monto."""
        metrics = get_webhook_metrics()
        
        metrics.inc_amount_mismatch("stripe")
        
        summary = metrics.get_summary()
        assert summary["amount_mismatch_total"]["stripe"] == 1

    def test_increment_credit_applied_counter(self):
        """Incrementa contador de créditos aplicados."""
        metrics = get_webhook_metrics()
        
        metrics.inc_credit_applied("paypal")
        metrics.inc_credit_applied("paypal")
        
        summary = metrics.get_summary()
        assert summary["credit_applied_total"]["paypal"] == 2

    def test_observe_processing_time(self):
        """Registra tiempo de procesamiento."""
        metrics = get_webhook_metrics()
        
        metrics.observe_processing_time("stripe", 100.5)
        metrics.observe_processing_time("stripe", 200.5)
        metrics.observe_processing_time("stripe", 150.5)
        
        summary = metrics.get_summary()
        assert summary["processing_times"]["stripe"]["count"] == 3
        assert summary["processing_times"]["stripe"]["p50"] > 0

    def test_track_processing_time_context_manager(self):
        """Context manager para tracking de tiempo."""
        import time
        metrics = get_webhook_metrics()
        
        with metrics.track_processing_time("stripe"):
            time.sleep(0.01)  # 10ms
        
        summary = metrics.get_summary()
        assert summary["processing_times"]["stripe"]["count"] == 1
        assert summary["processing_times"]["stripe"]["p50"] >= 10

    def test_prometheus_export_format(self):
        """Exporta en formato Prometheus."""
        metrics = get_webhook_metrics()
        
        metrics.inc_received("stripe")
        metrics.inc_verified("stripe", "success")
        
        prometheus_output = metrics.get_prometheus_metrics()
        
        assert 'webhook_received_total{provider="stripe"} 1' in prometheus_output
        assert 'webhook_verified_total{provider="stripe",result="success"} 1' in prometheus_output

    def test_reset_clears_all_metrics(self):
        """Reset limpia todas las métricas."""
        metrics = get_webhook_metrics()
        
        metrics.inc_received("stripe")
        metrics.inc_verified("stripe", "success")
        
        metrics.reset()
        
        summary = metrics.get_summary()
        assert len(summary["received_total"]) == 0
        assert len(summary["verified_total"]) == 0


# Fin del archivo backend/tests/modules/payments/test_phase3_hardening.py
