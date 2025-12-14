# -*- coding: utf-8 -*-
import os
import pytest
from pydantic import SecretStr

from app.shared.config.settings_base import BaseAppSettings

def test_database_url_builds_from_parts(monkeypatch):
    monkeypatch.setenv("DB_USER", "alice")
    monkeypatch.setenv("DB_PASSWORD", "s3cr3t!")
    monkeypatch.setenv("DB_HOST", "db.local")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "doxai_db")
    monkeypatch.setenv("DB_SSLMODE", "prefer")
    s = BaseAppSettings()
    assert s.database_url.startswith("postgresql+asyncpg://alice:")
    assert "db.local:5433/doxai_db" in s.database_url
    assert "sslmode=prefer" in s.database_url

def test_database_url_uses_DB_URL_and_normalizes(monkeypatch):
    monkeypatch.setenv("DB_URL", "postgres://u:p@h:5432/db")
    s = BaseAppSettings()
    assert s.database_url.startswith("postgresql+asyncpg://u:p@h:5432/db")
    assert "sslmode=" in s.database_url  # añade sslmode si faltaba

def test_cors_origins_parsing_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.com, https://b.com , 'http://localhost:8080'")
    s = BaseAppSettings()
    assert s.get_cors_origins() == ["https://a.com", "https://b.com", "http://localhost:8080"]

def test_cors_origins_wildcard(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    s = BaseAppSettings()
    assert s.get_cors_origins() == ["*"]

@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("", ["pdf","docx","doc","odt","xlsx","xls","ods","csv","pptx","ppt","odp","txt"]),
        ("pdf, docx ,  txt", ["pdf","docx","txt"]),
        ('["pdf","docx"]', ["pdf","docx"]),
    ],
)
def test_allowed_file_types_normalizer(monkeypatch, env_value, expected):
    if env_value is not None:
        monkeypatch.setenv("ALLOWED_FILE_TYPES", env_value)
    else:
        monkeypatch.delenv("ALLOWED_FILE_TYPES", raising=False)
    s = BaseAppSettings()
    assert s.allowed_file_types == expected

def test_payment_default_coherence_raises(monkeypatch):
    # PAYMENTS_DEFAULT=paypal pero paypal deshabilitado => debe fallar al correr checks
    monkeypatch.setenv("ENABLE_PAYPAL", "false")
    monkeypatch.setenv("ENABLE_STRIPE", "true")
    monkeypatch.setenv("PAYMENTS_DEFAULT", "paypal")

    from app.shared.config.settings_base import BaseAppSettings
    s = BaseAppSettings()
    with pytest.raises(ValueError) as ei:
        s._security_and_payments_checks()
    assert "PAYMENTS_DEFAULT=paypal" in str(ei.value)


def test_dev_soft_checks_dont_raise(monkeypatch, caplog):
    # En dev, mensajes informativos pero no excepción por JWT débil u OPENAI vacío
    monkeypatch.setenv("PYTHON_ENV", "development")
    monkeypatch.setenv("ENABLE_PAYPAL", "true")  # al menos un gateway
    s = BaseAppSettings()
    # Ejecuta los checks "suaves" invocados por el loader normalmente
    s._security_and_payments_checks()
    assert True  # No debe lanzar excepción

def test_prod_hard_checks_raise_when_invalid(monkeypatch):
    # En prod: DB_SSLMODE incorrecto y/o OPENAI_API_KEY faltante => debe fallar al correr checks
    monkeypatch.setenv("PYTHON_ENV", "production")
    monkeypatch.setenv("ENABLE_PAYPAL", "true")
    monkeypatch.setenv("PAYPAL_ENV", "live")
    monkeypatch.setenv("DB_SSLMODE", "disable")  # incorrecto en prod
    monkeypatch.setenv("JWT_SECRET_KEY", "X"*40)  # ok
    # Nota: no seteamos OPENAI_API_KEY para permitir que cualquiera de las 2 reglas dispare el error

    from app.shared.config.settings_base import BaseAppSettings
    s = BaseAppSettings()
    with pytest.raises(ValueError) as ei:
        s._security_and_payments_checks()
    msg = str(ei.value).lower()
    assert ("db_sslmode" in msg) or ("openai_api_key" in msg)
# Fin del archivo backend/tests/shared/config/test_settings_base.py