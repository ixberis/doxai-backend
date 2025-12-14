
# -*- coding: utf-8 -*-
import importlib
import types
import pytest

@pytest.mark.anyio
async def test_create_http_client_sets_headers_and_returns_true(monkeypatch):
    resources_mod = importlib.import_module("app.shared.core.resources_cache")
    http_client_mod = importlib.import_module("app.shared.core.http_client_cache")

    # Asegurar estado limpio
    resources_mod.resources.http_client = None

    # Dummy AsyncClient compatible con cualquier firma
    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers", {})
        async def aclose(self):
            pass

    # Stubs mínimos usados por el módulo (aceptan cualquier firma)
    def DummyTimeout(*args, **kwargs):
        return None

    def DummyLimits(*args, **kwargs):
        return None

    class DummyTransport:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    # Parchea el objeto 'httpx' que el módulo usa (httpx.AsyncClient, httpx.Timeout, etc.)
    monkeypatch.setattr(
        http_client_mod,
        "httpx",
        types.SimpleNamespace(
            AsyncClient=DummyClient,
            Timeout=DummyTimeout,
            Limits=DummyLimits,
            AsyncHTTPTransport=DummyTransport,
        ),
    )

    # 1) Parchea el objeto httpx completo usado por el módulo
    monkeypatch.setattr(
        http_client_mod,
        "httpx",
        types.SimpleNamespace(
            AsyncClient=DummyClient,
            Timeout=DummyTimeout,
            Limits=DummyLimits,
            AsyncHTTPTransport=DummyTransport,
        ),
    )

    # 2) Parchea también símbolos por nombre en el módulo, por si fueron importados así
    monkeypatch.setattr(http_client_mod, "AsyncClient", DummyClient, raising=False)
    monkeypatch.setattr(http_client_mod, "Timeout", DummyTimeout, raising=False)
    monkeypatch.setattr(http_client_mod, "Limits", DummyLimits, raising=False)
    monkeypatch.setattr(http_client_mod, "AsyncHTTPTransport", DummyTransport, raising=False)


    # Settings “seguros” (sin proxies)
    class DummySettings:
        app_name = "DoxAI"
        app_version = "0.0-test"
        http_extra_headers = {"X-Test": "1"}
        http_base_url = ""
        http_proxy = None
        http_no_proxy = None
        log_emoji = False
    # get_settings()
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.shared.config",
        types.SimpleNamespace(get_settings=lambda: DummySettings())
    )

    ok = await http_client_mod.create_http_client()
    assert ok is True
    assert resources_mod.resources.http_client is not None
    assert resources_mod.resources.http_client.headers.get("X-Test") == "1"
    assert "User-Agent" in resources_mod.resources.http_client.headers

@pytest.mark.anyio
async def test_get_http_client_creates_when_none(monkeypatch):
    resources_mod = importlib.import_module("app.shared.core.resources_cache")
    http_client_mod = importlib.import_module("app.shared.core.http_client_cache")

    # Asegurar estado
    resources_mod.resources.http_client = None

    # Evitar red: sustituimos create_http_client
    async def _fake_create():
        class DummyClient:
            def __init__(self):
                self.headers = {}
            async def aclose(self): ...
        resources_mod.resources.http_client = DummyClient()
        return True

    monkeypatch.setattr(http_client_mod, "create_http_client", _fake_create)
    client = await http_client_mod.get_http_client()
    assert client is resources_mod.resources.http_client
# backend/tests/shared/core/test_http_client_cache.py