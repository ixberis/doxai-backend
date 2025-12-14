
# -*- coding: utf-8 -*-
"""
backend/app/shared/config/settings_test.py

Overrides para entorno de PRUEBAS (test) usando Pydantic v2.
Busca ser determinista y seguro: logging moderado, base de datos aislada
y pasarelas de pago en modo prueba con claves dummy.

Autor: Ixchel Beristain
Fecha: 24/10/2025
"""

from pydantic import SecretStr
from .settings_base import BaseAppSettings
from pydantic_settings import SettingsConfigDict


class EnvTestingSettings(BaseAppSettings):
    # --- Identidad de entorno ---
    python_env: str = "test"

    # --- Logging en test: menos ruido ---
    log_level: str = "WARNING"
    log_format: str = "pretty"

    # --- Base de datos: usar DB separada para pruebas ---
    db_name: str = "doxai_test"
    # Si tu CI usa otra instancia/host, puedes sobreescribir por env vars:
    # db_host: str = "127.0.0.1"

    # --- Auth: tokens más cortos si te ayuda en tests de expiración ---
    # access_token_expire_minutes: int = 15

    # --- Pasarelas de pago ---
    # Para que el validador de seguridad pase sin depender de secretos reales,
    # habilitamos solo Stripe en modo test con valores dummy.
    enable_paypal: bool = False
    enable_stripe: bool = True
    payments_default: str = "stripe"  # "stripe" | "paypal"

    stripe_mode: str = "test"
    stripe_public_key: str = "pk_test_dummy"
    stripe_secret_key: SecretStr = SecretStr("sk_test_dummy")
    stripe_webhook_secret: SecretStr = SecretStr("whsec_test_dummy")

    # Si prefieres probar PayPal, cambia flags y usa sandbox:
    # enable_paypal: bool = True
    # enable_stripe: bool = False
    # payments_default: str = "paypal"
    # paypal_env: str = "sandbox"
    # paypal_client_id: str = "dummy"
    # paypal_client_secret: str = "dummy"

    model_config = SettingsConfigDict(
        env_file=".env.test",
        env_file_encoding="utf-8",
        extra="ignore",
    )


__all__ = False
# Fin del archivo backend\app\shared\config\settings_test.py