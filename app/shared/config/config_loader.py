# -*- coding: utf-8 -*-
"""
backend/app/shared/config/config_loader.py

Carga dinámica de configuración según PYTHON_ENV.
Ejecuta validaciones de seguridad y cachea la instancia (singleton).

Autor: Ixchel Beristain
Actualizado: 24/10/2025
"""

from functools import lru_cache
import os
from .settings_base import BaseAppSettings
from .settings_dev import DevSettings
from .settings_testing import EnvTestingSettings
from .settings_prod import ProdSettings


@lru_cache(maxsize=1)
def get_settings() -> BaseAppSettings:
    """
    Devuelve la configuración apropiada según PYTHON_ENV.
    
    Carga la subclase correcta (Dev/Test/Prod), ejecuta validaciones
    de seguridad y cachea el resultado como singleton.
    
    Returns:
        BaseAppSettings: Instancia de configuración para el entorno actual
        
    Raises:
        ValueError: Si las validaciones de seguridad fallan
    """
    env = os.getenv("PYTHON_ENV", "development").lower()
    
    if env == "production":
        settings = ProdSettings()
    elif env == "test":
        settings = EnvTestingSettings()
    else:
        settings = DevSettings()
    
    # Dispara validaciones específicas de seguridad y coherencia
    if hasattr(settings, "_security_and_payments_checks"):
        settings._security_and_payments_checks()
    
    return settings


__all__ = ["get_settings"]
# Fin del archivo