# -*- coding: utf-8 -*-
"""
backend/app/shared/config/settings_prod.py

Overrides para entorno de PRODUCCIÓN usando Pydantic v2.
Forza lectura solo desde variables de entorno / secret stores,
activa logging estable (INFO en JSON) y defaults seguros.

Autor: Ixchel Beristain
Fecha: 24/10/2025
"""

from typing import Literal
from .settings_base import BaseAppSettings
from pydantic_settings import SettingsConfigDict


class ProdSettings(BaseAppSettings):
    # --- Identidad de entorno ---
    python_env: Literal["development", "test", "production"] = "production"

    # --- Logging en prod: nivel estable y formato estructurado ---
    # Usa el mismo tipo Literal que BaseAppSettings para override correcto
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "pretty", "plain"] = "json"

    # --- Base de datos ---
    # En prod conviene SSL requerido (ajústalo si tu proveedor dicta otro valor)
    db_sslmode: str = "require"

    # --- Pasarelas de pago ---
    # No forzamos habilitación aquí (se define por env flags). Sí ajustamos modos.
    paypal_env: Literal["sandbox", "live"] = "live"
    stripe_mode: Literal["test", "live"] = "live"

    # Nota: el validador de BaseAppSettings exigirá secretos válidos y
    # al menos un gateway habilitado (ENABLE_PAYPAL/ENABLE_STRIPE).

    model_config = SettingsConfigDict(
        env_file=None,  # No leemos .env en producción
        extra="ignore",
    )


__all__ = ["ProdSettings"]
# Fin del archivo backend\app\shared\config\settings_prod.py