# -*- coding: utf-8 -*-
def test_resources_singleton_and_status():
    import importlib
    resources_mod = importlib.import_module("app.shared.core.resources_cache")

    # Misma instancia en toda la app
    r1 = resources_mod.resources
    r2 = resources_mod.resources
    assert r1 is r2

    # get_warmup_status retorna el objeto de estado
    status = resources_mod.get_warmup_status()
    assert hasattr(status, "is_ready")
# Fin del archivo