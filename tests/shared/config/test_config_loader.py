# -*- coding: utf-8 -*-
import importlib
import os
import pytest

from app.shared.config.config_loader import get_settings

def _reset_loader_cache():
    try:
        get_settings.cache_clear()
    except Exception:
        pass

def test_loader_returns_dev_by_default(monkeypatch):
    monkeypatch.delenv("PYTHON_ENV", raising=False)
    _reset_loader_cache()
    s = get_settings()
    assert s.is_dev is True
    assert s.python_env == "development"

def test_loader_selects_test(monkeypatch):
    monkeypatch.setenv("PYTHON_ENV", "test")
    _reset_loader_cache()
    s = get_settings()
    assert s.is_test is True
    assert s.python_env == "test"

def test_loader_selects_prod(monkeypatch):
    monkeypatch.setenv("PYTHON_ENV", "production")
    # Mínimos para pasar validaciones severas de prod
    monkeypatch.setenv("ENABLE_PAYPAL", "true")
    monkeypatch.setenv("PAYPAL_ENV", "live")
    monkeypatch.setenv("DB_SSLMODE", "require")
    monkeypatch.setenv("JWT_SECRET_KEY", "X"*40)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-xxx")
    _reset_loader_cache()
    s = get_settings()
    assert s.is_prod is True
    assert s.python_env == "production"

def test_loader_caches_singleton(monkeypatch):
    # Con cache: misma instancia entre llamadas.
    _reset_loader_cache()
    a = get_settings()
    b = get_settings()
    assert a is b

def test_security_checks_require_one_gateway(monkeypatch):
    # Fuerza ambos deshabilitados → debe levantar ValueError
    monkeypatch.setenv("ENABLE_PAYPAL", "false")
    monkeypatch.setenv("ENABLE_STRIPE", "false")
    _reset_loader_cache()
    with pytest.raises(ValueError) as ei:
        get_settings()
    assert "al menos un gateway" in str(ei.value).lower()
# Fin del archivo backend/tests/shared/config/test_config_loader.py