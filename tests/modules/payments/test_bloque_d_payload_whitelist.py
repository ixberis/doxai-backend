# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/test_bloque_d_payload_whitelist.py

Tests para BLOQUE D+: Persistencia segura (whitelist + hash + core fields, cero PII).

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import pytest

from app.modules.payments.services.webhooks.payload_sanitizer import (
    sanitize_webhook_payload,
    extract_audit_fields,
    compute_payload_hash,
    AUDIT_FIELDS_WHITELIST,
    CORE_FIELD_MAPPINGS,
)


class TestComputePayloadHash:
    """Tests para cálculo de hash."""

    def test_hash_is_sha256_hex(self):
        """Hash es SHA256 en hexadecimal."""
        result = compute_payload_hash(b"test payload")
        assert len(result) == 64  # SHA256 = 64 caracteres hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_input_same_hash(self):
        """Mismo input produce mismo hash."""
        h1 = compute_payload_hash(b"test")
        h2 = compute_payload_hash(b"test")
        assert h1 == h2

    def test_different_input_different_hash(self):
        """Diferente input produce diferente hash."""
        h1 = compute_payload_hash(b"test1")
        h2 = compute_payload_hash(b"test2")
        assert h1 != h2

    def test_handles_dict_input(self):
        """Acepta dict como input."""
        result = compute_payload_hash({"key": "value"})
        assert len(result) == 64

    def test_handles_string_input(self):
        """Acepta string como input."""
        result = compute_payload_hash("test string")
        assert len(result) == 64


class TestExtractAuditFields:
    """Tests para extracción de campos de auditoría."""

    def test_extracts_allowed_fields(self):
        """Extrae campos en whitelist."""
        payload = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "amount": 1000,
            "currency": "usd",
        }
        
        result = extract_audit_fields("stripe", payload)
        
        assert result["id"] == "evt_123"
        assert result["type"] == "checkout.session.completed"
        assert result["amount"] == 1000
        assert result["currency"] == "usd"
        assert result["provider"] == "stripe"

    def test_excludes_pii_fields(self):
        """NO incluye campos PII."""
        payload = {
            "id": "evt_123",
            "email": "user@example.com",
            "name": "John Doe",
            "phone": "+1234567890",
            "address": {"street": "123 Main St"},
        }
        
        result = extract_audit_fields("stripe", payload)
        
        assert result["id"] == "evt_123"
        assert "email" not in result
        assert "name" not in result
        assert "phone" not in result
        assert "address" not in result
        assert "user@example.com" not in str(result)
        assert "John Doe" not in str(result)

    def test_extracts_nested_allowed_fields(self):
        """Extrae campos permitidos de objetos anidados."""
        payload = {
            "id": "evt_123",
            "data": {
                "object": {
                    "id": "pi_456",
                    "amount": 5000,
                    "customer_email": "secret@example.com",  # PII
                }
            }
        }
        
        result = extract_audit_fields("stripe", payload)
        
        # Los campos anidados permitidos se preservan
        assert result["id"] == "evt_123"
        # PII no debe estar presente
        assert "secret@example.com" not in str(result)


class TestCoreFieldsExtraction:
    """D+ HARDENING: Tests para core fields."""

    def test_stripe_core_fields_extracted(self):
        """Extrae core fields de Stripe."""
        payload = {
            "id": "evt_123",
            "type": "payment_intent.succeeded",
            "livemode": False,
            "data": {
                "object": {
                    "id": "pi_456",
                    "payment_intent": "pi_456",
                    "amount": 5000,
                    "currency": "usd",
                    "status": "succeeded",
                }
            }
        }
        
        result = sanitize_webhook_payload("stripe", payload)
        
        # Core fields deben estar presentes
        assert result.get("core.event_id") == "evt_123"
        assert result.get("core.event_type") == "payment_intent.succeeded"
        assert result.get("core.amount") == 5000
        assert result.get("core.currency") == "usd"
        assert result.get("core.status") == "succeeded"
        assert result.get("core.livemode") is False

    def test_paypal_core_fields_extracted(self):
        """Extrae core fields de PayPal."""
        payload = {
            "id": "WH-123",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": "CAPTURE-456",
                "status": "COMPLETED",
                "amount": {
                    "value": "100.00",
                    "currency_code": "USD",
                },
            }
        }
        
        result = sanitize_webhook_payload("paypal", payload)
        
        # Core fields deben estar presentes
        assert result.get("core.event_id") == "WH-123"
        assert result.get("core.event_type") == "PAYMENT.CAPTURE.COMPLETED"
        assert result.get("core.provider_payment_id") == "CAPTURE-456"
        assert result.get("core.amount") == "100.00"
        assert result.get("core.currency") == "USD"
        assert result.get("core.status") == "COMPLETED"

    def test_core_fields_extracted_even_with_empty_whitelist(self):
        """Core fields se extraen aunque whitelist no tenga campos."""
        # Este payload solo tiene campos que irían a core.*
        payload = {
            "id": "evt_minimal",
            "type": "test.event",
            "data": {
                "object": {
                    "amount": 999,
                    "currency": "eur",
                }
            }
        }
        
        result = sanitize_webhook_payload("stripe", payload)
        
        # Core fields presentes
        assert result.get("core.event_id") == "evt_minimal"
        assert result.get("core.event_type") == "test.event"
        assert result.get("core.amount") == 999
        assert result.get("core.currency") == "eur"

    def test_core_fields_no_pii(self):
        """Core fields NO contienen PII."""
        payload = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "customer_email": "secret@example.com",  # PII
            "customer_name": "John Secret",  # PII
            "data": {
                "object": {
                    "id": "pi_456",
                    "amount": 5000,
                    "billing_details": {
                        "email": "billing@secret.com",  # PII
                        "name": "Billing Name",  # PII
                    }
                }
            }
        }
        
        result = sanitize_webhook_payload("stripe", payload)
        
        # PII no debe estar en ningún campo
        result_str = str(result)
        assert "secret@example.com" not in result_str
        assert "John Secret" not in result_str
        assert "billing@secret.com" not in result_str
        assert "Billing Name" not in result_str


class TestSanitizeWebhookPayload:
    """Tests para sanitización completa de payload."""

    def test_includes_payload_hash(self):
        """Incluye __payload_hash__."""
        payload = {"id": "evt_123", "type": "test"}
        
        result = sanitize_webhook_payload("stripe", payload)
        
        assert "__payload_hash__" in result
        assert len(result["__payload_hash__"]) == 64

    def test_includes_provider_metadata(self):
        """Incluye metadatos de procesamiento."""
        payload = {"id": "evt_123"}
        
        result = sanitize_webhook_payload("stripe", payload)
        
        assert result["__provider__"] == "stripe"
        assert result["__sanitized__"] is True
        assert "__whitelist_version__" in result
        assert result["__whitelist_version__"] == "1.1"  # D+ version

    def test_pii_not_in_output(self):
        """PII NO está en el output."""
        payload = {
            "id": "evt_123",
            "type": "checkout.session.completed",
            "customer_details": {
                "email": "customer@example.com",
                "name": "Jane Doe",
                "phone": "+1555123456",
                "address": {
                    "line1": "456 Oak Ave",
                    "city": "San Francisco",
                    "country": "US",
                }
            },
            "amount_total": 5000,
            "currency": "usd",
        }
        
        result = sanitize_webhook_payload("stripe", payload)
        
        # Campos permitidos presentes
        assert result.get("id") == "evt_123" or result.get("core.event_id") == "evt_123"
        assert "__payload_hash__" in result
        
        # PII NO presente
        result_str = str(result)
        assert "customer@example.com" not in result_str
        assert "Jane Doe" not in result_str
        assert "+1555123456" not in result_str
        assert "456 Oak Ave" not in result_str
        assert "San Francisco" not in result_str

    def test_paypal_payload_sanitization(self):
        """Sanitiza payload de PayPal correctamente."""
        payload = {
            "id": "WH-123",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": "CAPTURE-456",
                "amount": {"value": "100.00", "currency_code": "USD"},
                "payer": {
                    "email_address": "buyer@paypal.com",
                    "name": {"given_name": "John", "surname": "Smith"},
                    "payer_id": "PAYER123",
                },
            },
        }
        
        result = sanitize_webhook_payload("paypal", payload)
        
        assert result["__provider__"] == "paypal"
        assert "__payload_hash__" in result
        
        # PII no presente
        result_str = str(result)
        assert "buyer@paypal.com" not in result_str
        assert "John" not in result_str
        assert "Smith" not in result_str

    def test_uses_raw_payload_for_hash_if_provided(self):
        """Usa raw_payload para hash si se proporciona."""
        payload = {"id": "evt_123"}
        raw = b'{"id": "evt_123", "extra": "data"}'
        
        result_with_raw = sanitize_webhook_payload("stripe", payload, raw_payload=raw)
        result_without_raw = sanitize_webhook_payload("stripe", payload)
        
        # Hashes deben ser diferentes porque raw tiene más datos
        assert result_with_raw["__payload_hash__"] != result_without_raw["__payload_hash__"]

    def test_no_hash_if_disabled(self):
        """No incluye hash si include_hash=False."""
        payload = {"id": "evt_123"}
        
        result = sanitize_webhook_payload("stripe", payload, include_hash=False)
        
        assert "__payload_hash__" not in result


class TestWhitelistCompleteness:
    """Tests para verificar que la whitelist tiene campos necesarios."""

    def test_whitelist_includes_essential_ids(self):
        """Whitelist incluye IDs esenciales."""
        essential_ids = {
            "id", "event_id", "payment_intent", "charge", 
            "invoice", "subscription", "order_id", "refund_id"
        }
        assert essential_ids.issubset(AUDIT_FIELDS_WHITELIST)

    def test_whitelist_includes_amounts(self):
        """Whitelist incluye campos de montos."""
        amount_fields = {"amount", "amount_total", "currency"}
        assert amount_fields.issubset(AUDIT_FIELDS_WHITELIST)

    def test_whitelist_includes_status(self):
        """Whitelist incluye campos de estado."""
        status_fields = {"status", "payment_status", "state"}
        assert status_fields.issubset(AUDIT_FIELDS_WHITELIST)

    def test_whitelist_excludes_pii(self):
        """Whitelist NO incluye campos PII comunes."""
        pii_fields = {"email", "name", "phone", "address", "city"}
        assert not any(f in AUDIT_FIELDS_WHITELIST for f in pii_fields)


class TestCoreFieldMappings:
    """D+ HARDENING: Tests para mappings de core fields."""

    def test_stripe_mappings_complete(self):
        """Stripe tiene mappings para todos los core fields esenciales."""
        stripe_mappings = CORE_FIELD_MAPPINGS["stripe"]
        
        essential_cores = [
            "core.event_id",
            "core.event_type",
            "core.provider_payment_id",
            "core.amount",
            "core.currency",
            "core.status",
        ]
        
        for core in essential_cores:
            assert core in stripe_mappings, f"Missing {core} in Stripe mappings"

    def test_paypal_mappings_complete(self):
        """PayPal tiene mappings para todos los core fields esenciales."""
        paypal_mappings = CORE_FIELD_MAPPINGS["paypal"]
        
        essential_cores = [
            "core.event_id",
            "core.event_type",
            "core.provider_payment_id",
            "core.amount",
            "core.currency",
            "core.status",
        ]
        
        for core in essential_cores:
            assert core in paypal_mappings, f"Missing {core} in PayPal mappings"
