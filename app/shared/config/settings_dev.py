
# -*- coding: utf-8 -*-
"""
backend/app/shared/config/settings_dev.py

Overrides para entorno de DESARROLLO (dev) usando Pydantic v2.
Hereda de BaseAppSettings y ajusta únicamente valores específicos
del ambiente local de desarrollo.

Autor: Ixchel Beristain
Fecha: 24/10/2025
"""

from typing import Optional

from pydantic_settings import SettingsConfigDict

from .settings_base import BaseAppSettings


class DevSettings(BaseAppSettings):
    """Configuración para entorno de desarrollo."""

    # Entorno
    python_env: str = "development"

    # Logging
    log_level: str = "DEBUG"
    log_format: str = "plain"  # formato legible en consola

    # Base de datos
    db_sslmode: str = "disable"  # en desarrollo no se requiere SSL

    # Pasarelas de pago (habilitadas en desarrollo)
    enable_paypal: bool = True
    enable_stripe: bool = True
    payments_default: str = "stripe"  # coherente con gateways habilitados

    # PayPal en sandbox durante dev
    paypal_env: str = "sandbox"

    # Stripe en modo test durante dev
    stripe_mode: str = "test"

    # -------------------------------------------------------------------------
    # 🔧 Sentry opcional en entorno local
    # -------------------------------------------------------------------------
    # En desarrollo NO es necesario un DSN válido.
    # Si viene vacío desde el entorno (""), lo aceptamos como str sin validar URL.
    SENTRY_DSN: Optional[str] = None

    # Configuración de carga de variables de entorno
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


__all__ = ["DevSettings"]

# Fin del archivo backend/app/shared/config/settings_dev.py
