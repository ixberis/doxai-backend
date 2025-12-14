# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/facades/webhooks/constants.py

Constantes para webhooks Stripe/PayPal.
"""

# Stripe events
STRIPE_EVENT_SUCCESS = ["checkout.session.completed", "payment_intent.succeeded", "charge.succeeded"]
STRIPE_EVENT_FAILED = ["payment_intent.payment_failed", "charge.failed"]
STRIPE_EVENT_REFUND = ["charge.refunded", "refund.created"]

# PayPal events
PAYPAL_EVENT_SUCCESS = ["PAYMENT.CAPTURE.COMPLETED", "CHECKOUT.ORDER.COMPLETED"]
PAYPAL_EVENT_FAILED = ["PAYMENT.CAPTURE.DENIED"]
PAYPAL_EVENT_REFUND = ["PAYMENT.CAPTURE.REFUNDED"]

STRIPE_SUCCESS_EVENTS = set(STRIPE_EVENT_SUCCESS)
PAYPAL_SUCCESS_EVENTS = set(PAYPAL_EVENT_SUCCESS)

__all__ = [
    "STRIPE_EVENT_SUCCESS", "STRIPE_EVENT_FAILED", "STRIPE_EVENT_REFUND",
    "PAYPAL_EVENT_SUCCESS", "PAYPAL_EVENT_FAILED", "PAYPAL_EVENT_REFUND",
    "STRIPE_SUCCESS_EVENTS", "PAYPAL_SUCCESS_EVENTS",
]
