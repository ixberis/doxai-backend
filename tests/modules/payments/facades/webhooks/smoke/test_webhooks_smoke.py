# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/facades/test_webhooks_smoke.py

Smoke test para verificar exports de webhooks facade.

Autor: DoxAI
Fecha: 26/10/2025
"""

import pytest


def test_webhooks_facade_exports():
    """Verifica que el facade de webhooks exporte correctamente las funciones públicas."""
    from app.modules.payments.facades.webhooks import (
        verify_and_handle_webhook,
        is_success_event,
        is_refund_event,
        normalize_webhook_data,
    )
    
    # Verificar que las funciones son callables
    assert callable(verify_and_handle_webhook)
    assert callable(is_success_event)
    assert callable(is_refund_event)
    assert callable(normalize_webhook_data)


def test_is_success_event_stripe():
    """Verifica que is_success_event identifica correctamente eventos exitosos de Stripe."""
    from app.modules.payments.facades.webhooks import is_success_event
    from app.modules.payments.enums import PaymentProvider
    
    # Eventos de éxito
    assert is_success_event(PaymentProvider.STRIPE, "checkout.session.completed") is True
    assert is_success_event(PaymentProvider.STRIPE, "payment_intent.succeeded") is True
    assert is_success_event(PaymentProvider.STRIPE, "charge.succeeded") is True
    
    # Eventos que no son de éxito
    assert is_success_event(PaymentProvider.STRIPE, "charge.failed") is False
    assert is_success_event(PaymentProvider.STRIPE, "charge.refunded") is False
    assert is_success_event(PaymentProvider.STRIPE, "") is False


def test_is_success_event_paypal():
    """Verifica que is_success_event identifica correctamente eventos exitosos de PayPal."""
    from app.modules.payments.facades.webhooks import is_success_event
    from app.modules.payments.enums import PaymentProvider
    
    # Eventos de éxito
    assert is_success_event(PaymentProvider.PAYPAL, "PAYMENT.CAPTURE.COMPLETED") is True
    assert is_success_event(PaymentProvider.PAYPAL, "CHECKOUT.ORDER.APPROVED") is True
    
    # Eventos que no son de éxito
    assert is_success_event(PaymentProvider.PAYPAL, "PAYMENT.CAPTURE.REFUNDED") is False
    assert is_success_event(PaymentProvider.PAYPAL, "PAYMENT.REFUND.FAILED") is False
    assert is_success_event(PaymentProvider.PAYPAL, "") is False


def test_is_refund_event_stripe():
    """Verifica que is_refund_event identifica correctamente eventos de reembolso de Stripe."""
    from app.modules.payments.facades.webhooks import is_refund_event
    from app.modules.payments.enums import PaymentProvider
    
    # Eventos de reembolso
    assert is_refund_event(PaymentProvider.STRIPE, "charge.refunded") is True
    assert is_refund_event(PaymentProvider.STRIPE, "refund.created") is True
    assert is_refund_event(PaymentProvider.STRIPE, "refund.updated") is True
    assert is_refund_event(PaymentProvider.STRIPE, "refund.failed") is True
    
    # Eventos que no son de reembolso
    assert is_refund_event(PaymentProvider.STRIPE, "charge.succeeded") is False
    assert is_refund_event(PaymentProvider.STRIPE, "") is False


def test_is_refund_event_paypal():
    """Verifica que is_refund_event identifica correctamente eventos de reembolso de PayPal."""
    from app.modules.payments.facades.webhooks import is_refund_event
    from app.modules.payments.enums import PaymentProvider
    
    # Eventos de reembolso
    assert is_refund_event(PaymentProvider.PAYPAL, "PAYMENT.CAPTURE.REFUNDED") is True
    assert is_refund_event(PaymentProvider.PAYPAL, "PAYMENT.REFUND.COMPLETED") is True
    assert is_refund_event(PaymentProvider.PAYPAL, "PAYMENT.REFUND.FAILED") is True
    
    # Eventos que no son de reembolso
    assert is_refund_event(PaymentProvider.PAYPAL, "PAYMENT.CAPTURE.COMPLETED") is False
    assert is_refund_event(PaymentProvider.PAYPAL, "") is False


def test_webhook_handler_import():
    """Verifica que webhook_handler puede importar is_success_event sin ciclos."""
    # Este import dinámico es el que se hace en webhook_handler.py línea 196
    from app.modules.payments.facades.webhooks import is_success_event
    from app.modules.payments.enums import PaymentProvider
    
    # Verificar que funciona
    result = is_success_event(PaymentProvider.STRIPE, "charge.succeeded")
    assert result is True


# Fin del archivo
