# -*- coding: utf-8 -*-
import os
from app.shared.config.settings_dev import DevSettings
from app.shared.config.settings_testing import EnvTestingSettings
from app.shared.config.settings_prod import ProdSettings

def test_dev_overrides_defaults():
    s = DevSettings()
    assert s.is_dev
    assert s.log_level.upper() == "DEBUG"
    assert s.log_format in ("plain", "pretty")  # plain por defecto
    assert s.db_sslmode == "disable"
    assert s.enable_paypal is True and s.enable_stripe is True
    assert s.payments_default == "stripe"
    assert s.paypal_env == "sandbox"
    assert s.stripe_mode == "test"

def test_test_overrides_defaults(monkeypatch):
    monkeypatch.setenv("PYTHON_ENV", "test")
    s = EnvTestingSettings()
    assert s.is_test
    assert s.db_name.endswith("_test")
    assert s.enable_stripe is True and s.enable_paypal is False
    assert s.payments_default == "stripe"
    assert s.stripe_mode == "test"
    # claves dummy presentes para pasar validaciones en CI si hiciera falta
    assert s.stripe_public_key.startswith("pk_test")
    assert s.stripe_secret_key.get_secret_value().startswith("sk_test")
    assert s.stripe_webhook_secret.get_secret_value().startswith("whsec_")

def test_prod_overrides_defaults(monkeypatch):
    monkeypatch.setenv("PYTHON_ENV", "production")
    # Limpiar variables de logging para verificar defaults de ProdSettings
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    # Satisface mínimos duros para que inicialice
    monkeypatch.setenv("ENABLE_PAYPAL", "true")
    monkeypatch.setenv("PAYPAL_ENV", "live")
    monkeypatch.setenv("DB_SSLMODE", "require")
    monkeypatch.setenv("JWT_SECRET_KEY", "X"*40)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-xxx")

    s = ProdSettings()
    assert s.is_prod
    assert s.log_level.upper() == "INFO"
    assert s.log_format == "json"
    assert s.db_sslmode == "require"
# Fin del archivo backend/tests/shared/config/test_settings_base.py