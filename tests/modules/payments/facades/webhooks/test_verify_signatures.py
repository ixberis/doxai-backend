# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/facades/webhooks/test_verify_signatures.py

Tests para verificación de firmas de webhooks.

Autor: DoxAI
Fecha: 2025-12-13
"""
import hmac
import hashlib
import time
import pytest

from app.modules.payments.facades.webhooks.verify import verify_stripe_signature


def _make_stripe_sig(payload: bytes, secret: str, ts: int) -> str:
    """Genera una firma Stripe válida para testing."""
    signed = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), msg=signed, digestmod=hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


class TestVerifyStripeSignature:
    """Tests para verificación de firma de Stripe."""

    def test_verify_stripe_signature_ok(self, monkeypatch):
        """Firma válida retorna True."""
        secret = "whsec_test_123"
        payload = b'{"type":"payment_intent.succeeded"}'
        ts = int(time.time())
        sig = _make_stripe_sig(payload, secret, ts)
        
        class MockSettings:
            stripe_webhook_secret = secret
            stripe_webhook_tolerance_seconds = 300

        # Forzar que NO sea entorno de desarrollo para probar verificación real
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PYTHON_ENV", "production")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
        
        monkeypatch.setattr(
            "app.modules.payments.facades.webhooks.verify.get_payments_settings",
            lambda: MockSettings(),
        )
        
        headers = {"Stripe-Signature": sig}
        result = verify_stripe_signature(payload, headers)
        assert result is True

    def test_verify_stripe_signature_bad_sig(self, monkeypatch):
        """Firma inválida retorna False."""
        secret = "whsec_test_123"
        payload = b'{"type":"payment_intent.succeeded"}'
        ts = int(time.time())
        bad_sig = f"t={ts},v1={'0' * 64}"
        
        class MockSettings:
            stripe_webhook_secret = secret
            stripe_webhook_tolerance_seconds = 300

        # Forzar que NO sea entorno de desarrollo
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PYTHON_ENV", "production")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
        
        monkeypatch.setattr(
            "app.modules.payments.facades.webhooks.verify.get_payments_settings",
            lambda: MockSettings(),
        )
        
        headers = {"Stripe-Signature": bad_sig}
        result = verify_stripe_signature(payload, headers)
        assert result is False

    def test_verify_stripe_signature_missing_header(self, monkeypatch):
        """Sin header de firma retorna False."""
        secret = "whsec_test_123"
        payload = b'{"type":"payment_intent.succeeded"}'
        
        class MockSettings:
            stripe_webhook_secret = secret
            stripe_webhook_tolerance_seconds = 300

        # Forzar que NO sea entorno de desarrollo
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PYTHON_ENV", "production")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
        
        monkeypatch.setattr(
            "app.modules.payments.facades.webhooks.verify.get_payments_settings",
            lambda: MockSettings(),
        )
        
        headers = {}  # No signature header
        result = verify_stripe_signature(payload, headers)
        assert result is False

    def test_verify_stripe_signature_case_insensitive_header(self, monkeypatch):
        """Header de firma es case-insensitive."""
        secret = "whsec_test_123"
        payload = b'{"type":"payment_intent.succeeded"}'
        ts = int(time.time())
        sig = _make_stripe_sig(payload, secret, ts)
        
        class MockSettings:
            stripe_webhook_secret = secret
            stripe_webhook_tolerance_seconds = 300

        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("PYTHON_ENV", "production")
        monkeypatch.setenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false")
        
        monkeypatch.setattr(
            "app.modules.payments.facades.webhooks.verify.get_payments_settings",
            lambda: MockSettings(),
        )
        
        # Lowercase header
        headers = {"stripe-signature": sig}
        result = verify_stripe_signature(payload, headers)
        assert result is True


# Fin del archivo
