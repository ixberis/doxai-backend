# -*- coding: utf-8 -*-
import os
import importlib
import functools
import pytest

@pytest.fixture(autouse=True)
def _isolate_env_and_cache(monkeypatch):
    """
    Aísla variables de entorno y limpia el caché de get_settings() en cada test.
    """
    # Asegura que no heredamos PYTHON_ENV ni secretos del shell del dev
    for k in list(os.environ.keys()):
        if k.startswith(("DB_", "JWT_", "OPENAI_", "STRIPE_", "PAYPAL_", "EMAIL_", "CORS_", "APP_", "CACHE_EVICTION_", "REDIS_", "SUPABASE_", "HTTP_", "LOGIN_", "PAYMENTS_")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PYTHON_ENV", "development")

    # Recargar módulos para garantizar estado limpio
    import app.shared.config.config_loader as config_loader
    try:
        functools.lru_cache.clear_cache(config_loader.get_settings)  # pydantic v2 py3.12?
    except Exception:
        try:
            config_loader.get_settings.cache_clear()
        except Exception:
            pass
    importlib.reload(config_loader)

    # Limpiar singleton de PaymentsSettings
    import app.shared.config.settings_payments as settings_payments
    settings_payments._payments_settings = None

    yield

    # Limpieza final
    try:
        config_loader.get_settings.cache_clear()
    except Exception:
        pass
    settings_payments._payments_settings = None
# Fin del archivo backend/tests/shared/config/conftest.py