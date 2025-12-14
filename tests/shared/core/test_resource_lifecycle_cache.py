# -*- coding: utf-8 -*-
import types
import pytest

@pytest.mark.anyio
async def test_shutdown_all_closes_http_and_resets_state():
    import importlib
    resources_mod = importlib.import_module("app.shared.core.resources_cache")
    lifecycle_mod = importlib.import_module("app.shared.core.resource_lifecycle_cache")

    closed = {"ok": False}
    class DummyClient:
        async def aclose(self):
            closed["ok"] = True

    # Sembrar estado
    resources_mod.resources.http_client = DummyClient()
    resources_mod.resources.warmup_completed = True

    await lifecycle_mod.shutdown_all()

    assert closed["ok"] is True
    assert resources_mod.resources.http_client is None
    assert resources_mod.resources.warmup_completed is False
# Fin del archivo