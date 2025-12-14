
# -*- coding: utf-8 -*-
import importlib
import types
import pytest

@pytest.mark.anyio
async def test_create_app_and_lifespan(monkeypatch):
    app_module = importlib.import_module("app.shared.core.app")

    # Evitar que la factoría intente cargar routers de todos los módulos
    monkeypatch.setattr(app_module, "_include_module_routers", lambda app: None)

    # Neutralizar warmup/shutdown pesados
    async def _fake_run_warmup_once():
        class S:
            is_ready = True
        return S()
    async def _fake_shutdown_all():
        return None

    monkeypatch.setitem(
        __import__('sys').modules,
        'app.shared.core.resource_cache',
        types.SimpleNamespace(
            run_warmup_once=_fake_run_warmup_once,
            shutdown_all=_fake_shutdown_all
        )
    )

    fastapi_app = app_module.create_app()
    assert fastapi_app.title.startswith("DoxAI Backend")

    async with app_module.lifespan(fastapi_app):
        pass
# backend/tests/shared/core/test_app_factory.py