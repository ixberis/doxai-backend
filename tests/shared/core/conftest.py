# -*- coding: utf-8 -*-
# conftest.py — fixtures y utilidades comunes para core

import types
import asyncio
import contextlib
import pytest

class DummySettings:
    # Valores por defecto “seguros” y consistentes con los módulos core
    app_name = "DoxAI"
    app_version = "0.0-test"
    http_extra_headers = {"X-Test": "1"}
    http_base_url = ""           # evitar base_url inválidas
    http_proxy = None
    http_no_proxy = None

    warmup_enable = True
    warmup_silence_pdfminer = False
    warmup_preload_fast = False
    warmup_preload_hires = False
    warmup_preload_table_model = False
    warmup_timeout_sec = 2

    warmup_http_client = False
    warmup_http_health_check = False
    warmup_http_health_url = ""
    warmup_http_health_timeout_sec = 2
    warmup_http_health_warn_ms = 600
    log_emoji = False


@pytest.fixture
def dummy_settings():
    return DummySettings()


@pytest.fixture
def patch_get_settings(monkeypatch, dummy_settings):
    """
    Parchea app.shared.config.get_settings para que devuelva DummySettings.
    """
    def _get_settings():
        return dummy_settings
    # Ruta usada por los módulos core
    monkeypatch.setitem(__import__('sys').modules, 'app.shared.config', types.SimpleNamespace(get_settings=_get_settings))
    return dummy_settings


@pytest.fixture
def no_sleep(monkeypatch):
    """
    Evita esperas reales en backoff (hace que asyncio.sleep sea no-op).
    """
    async def _noop(_):
        return None
    monkeypatch.setattr("asyncio.sleep", _noop)
    return True


@pytest.fixture
def anyio_backend():
    # Permite usar @pytest.mark.anyio en tests async
    return "asyncio"
# Fin del archivo