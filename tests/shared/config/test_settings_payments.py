# -*- coding: utf-8 -*-
"""
backend/tests/shared/config/test_settings_payments.py

Tests de configuración de pagos.

Autor: DoxAI
Fecha: 26/10/2025
"""

import pytest
from app.shared.config.settings_payments import PaymentsSettings, get_payments_settings


def test_payments_settings_defaults():
    """Verifica que PaymentsSettings tiene defaults seguros."""
    settings = PaymentsSettings(_env_file=None)  # Skip .env file to test pure defaults
    
    # Feature flags
    assert settings.payments_enabled is True
    assert settings.refunds_enabled is True
    assert settings.stripe_enabled is True
    assert settings.paypal_enabled is True
    
    # Idempotencia
    assert settings.payments_idempotency_salt == ""  # Default vacío, debe configurarse en producción
    assert settings.payments_idempotency_hex_length == 32
    
    # Límites
    assert settings.min_payment_amount_cents == 100
    assert settings.max_payment_amount_cents == 10_000_000
    assert settings.min_refund_amount_cents == 1
    assert settings.allow_partial_refunds is True
    assert settings.max_refunds_per_payment == 10
    
    # Timeouts
    assert settings.payment_session_timeout_minutes == 30
    assert settings.webhook_processing_timeout_seconds == 30
    assert settings.refund_processing_timeout_seconds == 60
    assert settings.max_webhook_retries == 3
    
    # Seguridad
    assert settings.allow_insecure_webhooks is False
    assert settings.require_idempotency_keys is True
    assert settings.payments_allow_http_local is True  # Solo desarrollo
    assert settings.use_payment_stubs is True  # Desarrollo, debe ser False en prod
    
    # Créditos
    assert settings.credits_per_dollar == 100
    assert settings.welcome_credits == 50
    
    # Notificaciones
    assert settings.send_payment_confirmation_email is True
    assert settings.send_refund_notification_email is True


def test_payments_settings_stripe_defaults():
    """Verifica defaults de configuración de Stripe."""
    settings = PaymentsSettings(_env_file=None)
    
    assert settings.stripe_secret_key is None  # Debe configurarse
    assert settings.stripe_publishable_key is None  # Debe configurarse
    assert settings.stripe_webhook_secret is None  # Debe configurarse
    assert settings.stripe_webhook_tolerance_seconds == 300  # 5 minutos


def test_payments_settings_paypal_defaults():
    """Verifica defaults de configuración de PayPal."""
    settings = PaymentsSettings(_env_file=None)
    
    assert settings.paypal_client_id is None  # Debe configurarse
    assert settings.paypal_client_secret is None  # Debe configurarse
    assert settings.paypal_mode == "sandbox"  # Default desarrollo
    assert settings.paypal_webhook_id is None  # Debe configurarse


def test_get_payments_settings_singleton():
    """Verifica que get_payments_settings devuelve un singleton."""
    settings1 = get_payments_settings()
    settings2 = get_payments_settings()
    
    assert settings1 is settings2
    assert isinstance(settings1, PaymentsSettings)


def test_payments_settings_validation_limits():
    """Verifica que los límites de validación son sensatos."""
    settings = PaymentsSettings(_env_file=None)
    
    # Monto mínimo es razonable (1 USD/MXN)
    assert settings.min_payment_amount_cents >= 100
    
    # Monto máximo es razonable (100k USD/MXN)
    assert settings.max_payment_amount_cents <= 100_000_000
    
    # Min < Max
    assert settings.min_payment_amount_cents < settings.max_payment_amount_cents
    
    # Reembolso mínimo es positivo
    assert settings.min_refund_amount_cents > 0


def test_payments_settings_security_defaults():
    """Verifica que los defaults de seguridad son seguros para producción."""
    settings = PaymentsSettings(_env_file=None)
    
    # En producción, estos deben ser False
    assert settings.allow_insecure_webhooks is False  # ✅ Seguro
    
    # En desarrollo, estos pueden ser True
    # Documentar que deben cambiar en prod
    assert settings.payments_allow_http_local is True  # ⚠️ Solo desarrollo
    assert settings.use_payment_stubs is True  # ⚠️ Solo desarrollo


def test_payments_settings_idempotency_config():
    """Verifica configuración de idempotencia."""
    settings = PaymentsSettings(_env_file=None)
    
    # Salt vacío por defecto (debe configurarse con valor secreto en prod)
    assert isinstance(settings.payments_idempotency_salt, str)
    
    # Longitud de hash razonable
    assert settings.payments_idempotency_hex_length == 32
    assert settings.payments_idempotency_hex_length >= 16  # Mínimo recomendado


def test_payments_settings_timeout_config():
    """Verifica que los timeouts son razonables."""
    settings = PaymentsSettings(_env_file=None)
    
    # Timeouts positivos
    assert settings.payment_session_timeout_minutes > 0
    assert settings.webhook_processing_timeout_seconds > 0
    assert settings.refund_processing_timeout_seconds > 0
    
    # Orden de magnitud razonable
    assert settings.webhook_processing_timeout_seconds <= 60  # Max 1 minuto
    assert settings.refund_processing_timeout_seconds <= 120  # Max 2 minutos
    
    # Reintentos razonables
    assert 1 <= settings.max_webhook_retries <= 5


def test_payments_settings_credits_config():
    """Verifica configuración de créditos."""
    settings = PaymentsSettings(_env_file=None)
    
    # Conversión positiva
    assert settings.credits_per_dollar > 0
    
    # Créditos de bienvenida razonables
    assert settings.welcome_credits >= 0
    assert settings.welcome_credits <= 1000  # No demasiado generoso


# Fin del archivo
