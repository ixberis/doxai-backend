# -*- coding: utf-8 -*-
"""
backend/app/shared/config/settings_payments.py

Configuración de pagos y reembolsos para DoxAI.

Descripción:
    Centraliza configuración de proveedores de pago, límites,
    tiempos de espera y features flags.

Autor: DoxAI
Fecha: 25/10/2025
"""

from __future__ import annotations

import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PaymentsSettings(BaseSettings):
    """Configuración de sistema de pagos."""
    
    # =========================================================================
    # FEATURE FLAGS
    # =========================================================================
    
    payments_enabled: bool = Field(
        default=True,
        description="Habilita el sistema de pagos globalmente"
    )
    
    refunds_enabled: bool = Field(
        default=True,
        description="Habilita el sistema de reembolsos"
    )
    
    # =========================================================================
    # STRIPE
    # =========================================================================
    
    stripe_enabled: bool = Field(
        default=True,
        description="Habilita pagos con Stripe"
    )
    
    stripe_secret_key: Optional[str] = Field(
        default=None,
        description="Stripe secret key (sk_live_... o sk_test_...)"
    )
    
    # =========================================================================
    # FRONTEND URL (normalizado desde FRONTEND_URL o FRONTEND_BASE_URL)
    # =========================================================================
    
    frontend_url: Optional[str] = Field(
        default=None,
        description="URL base del frontend para redirects de checkout"
    )
    
    @field_validator('stripe_secret_key', mode='before')
    @classmethod
    def _load_stripe_secret_key(cls, v: Optional[str]) -> Optional[str]:
        """Fallback a STRIPE_SECRET_KEY env var si no está en settings."""
        if v:
            return v
        return os.getenv("STRIPE_SECRET_KEY")
    
    @field_validator('frontend_url', mode='before')
    @classmethod
    def _load_frontend_url(cls, v: Optional[str]) -> Optional[str]:
        """Fallback a FRONTEND_URL o FRONTEND_BASE_URL."""
        if v:
            return v
        return os.getenv("FRONTEND_URL") or os.getenv("FRONTEND_BASE_URL")
    
    stripe_publishable_key: Optional[str] = Field(
        default=None,
        description="Stripe publishable key (pk_live_... o pk_test_...)"
    )
    
    stripe_webhook_secret: Optional[str] = Field(
        default=None,
        description="Stripe webhook signing secret (whsec_...)"
    )
    
    stripe_webhook_tolerance_seconds: int = Field(
        default=300,
        description="Tolerancia para validación de timestamp de webhooks Stripe (5 minutos)"
    )
    
    # =========================================================================
    # PAYPAL
    # =========================================================================
    
    paypal_enabled: bool = Field(
        default=True,
        description="Habilita pagos con PayPal"
    )
    
    paypal_client_id: Optional[str] = Field(
        default=None,
        description="PayPal client ID"
    )
    
    paypal_client_secret: Optional[str] = Field(
        default=None,
        description="PayPal client secret"
    )
    
    paypal_mode: str = Field(
        default="sandbox",
        description="Modo de PayPal: 'sandbox' o 'live'"
    )
    
    paypal_webhook_id: Optional[str] = Field(
        default=None,
        description="PayPal webhook ID para validación de firmas"
    )
    
    # =========================================================================
    # LÍMITES Y VALIDACIONES
    # =========================================================================
    
    min_payment_amount_cents: int = Field(
        default=100,
        description="Monto mínimo de pago en centavos (1.00 USD/MXN)"
    )
    
    max_payment_amount_cents: int = Field(
        default=10_000_000,
        description="Monto máximo de pago en centavos (100,000 USD/MXN)"
    )
    
    min_refund_amount_cents: int = Field(
        default=1,
        description="Monto mínimo de reembolso en centavos"
    )
    
    allow_partial_refunds: bool = Field(
        default=True,
        description="Permite reembolsos parciales"
    )
    
    max_refunds_per_payment: int = Field(
        default=10,
        description="Máximo número de reembolsos permitidos por pago"
    )
    
    # =========================================================================
    # TIMEOUTS Y REINTENTOS
    # =========================================================================
    
    payment_session_timeout_minutes: int = Field(
        default=30,
        description="Tiempo de expiración de sesiones de pago (minutos)"
    )
    
    webhook_processing_timeout_seconds: int = Field(
        default=30,
        description="Timeout para procesamiento de webhooks"
    )
    
    refund_processing_timeout_seconds: int = Field(
        default=60,
        description="Timeout para procesamiento de reembolsos"
    )
    
    max_webhook_retries: int = Field(
        default=3,
        description="Máximo número de reintentos para webhooks fallidos"
    )
    
    # =========================================================================
    # SEGURIDAD
    # =========================================================================
    
    allow_insecure_webhooks: bool = Field(
        default=False,
        description="Permite webhooks sin validación de firma (SOLO DESARROLLO)"
    )
    
    require_idempotency_keys: bool = Field(
        default=True,
        description="Requiere idempotency_key en operaciones críticas"
    )
    
    payments_idempotency_salt: str = Field(
        default="",
        description="Salt para endurecer generación de claves de idempotencia"
    )
    
    payments_idempotency_hex_length: int = Field(
        default=32,
        description="Longitud del hash hexadecimal para idempotency_key"
    )
    
    payments_allow_http_local: bool = Field(
        default=True,
        description="Permite URLs HTTP para localhost en validación de redirects (solo desarrollo)"
    )
    
    use_payment_stubs: bool = Field(
        default=True,
        description="Usa stubs de proveedores (False = requiere adaptadores reales en producción)"
    )
    
    # =========================================================================
    # CRÉDITOS
    # =========================================================================
    
    credits_per_dollar: int = Field(
        default=100,
        description="Créditos otorgados por cada dólar (1 USD = 100 créditos)"
    )
    
    welcome_credits: int = Field(
        default=50,
        description="Créditos de bienvenida para nuevos usuarios"
    )
    
    # =========================================================================
    # NOTIFICACIONES
    # =========================================================================
    
    send_payment_confirmation_email: bool = Field(
        default=True,
        description="Enviar email de confirmación al completar pago"
    )
    
    send_refund_notification_email: bool = Field(
        default=True,
        description="Enviar email de notificación al procesar reembolso"
    )
    
    # =========================================================================
    # CONFIGURACIÓN DE PYDANTIC
    # =========================================================================
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton global
_payments_settings: Optional[PaymentsSettings] = None


def get_payments_settings() -> PaymentsSettings:
    """
    Obtiene la instancia global de configuración de pagos.
    
    Returns:
        PaymentsSettings: Configuración de pagos
    """
    global _payments_settings
    if _payments_settings is None:
        _payments_settings = PaymentsSettings()
    return _payments_settings


__all__ = [
    "PaymentsSettings",
    "get_payments_settings",
]
# Fin del archivo backend/app/shared/config/settings_payments.py
