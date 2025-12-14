
# -*- coding: utf-8 -*-
"""
backend/app/core/settings.py

Fachada de configuración para DoxAI 2.0.
Reexpone la carga de settings basada en Pydantic v2 definida en
`app.shared.config`, alineada con la arquitectura descrita en la
documentación técnica de DoxAI. 

Autor: Ixchel Beristain
Fecha: 2025-11-17
"""

from typing import cast

from app.shared.config.config_loader import get_settings as _get_settings
from app.shared.config.settings_base import BaseAppSettings


def get_settings() -> BaseAppSettings:
    """
    Devuelve la configuración global de la aplicación.

    Esta función encapsula `app.shared.config.config_loader.get_settings`
    para ofrecer un punto de entrada estable bajo `app.core.settings`.

    Returns:
        BaseAppSettings: instancia de configuración (según PYTHON_ENV).
    """
    settings = _get_settings()
    return cast(BaseAppSettings, settings)

# Fin del archivo backend\app\core\settings.py