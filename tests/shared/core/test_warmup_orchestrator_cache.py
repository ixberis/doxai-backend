# -*- coding: utf-8 -*-
import types
import pathlib
import pytest

@pytest.mark.anyio
async def test_run_warmup_once_minimal_path(patch_get_settings, monkeypatch, tmp_path):
    # Ajustar flags mínimos: no hacer precargas pesadas ni cliente http
    settings = patch_get_settings
    settings.warmup_enable = True
    settings.warmup_preload_fast = False
    settings.warmup_preload_hires = False
    settings.warmup_preload_table_model = False
    settings.warmup_http_client = False
    settings.warmup_http_health_check = False

    # Parchear verificadores (opcionales; no influyen en is_ready)
    from app.shared.core import warmup_orchestrator_cache as W

    monkeypatch.setattr(W, "check_tesseract_availability", lambda: True)
    monkeypatch.setattr(W, "check_ghostscript_availability", lambda: (True, "/bin/gs"))
    monkeypatch.setattr(W, "check_poppler_availability", lambda: (True, "/bin/pdftoppm"))

    # Asset de warm-up “presente”
    asset = tmp_path / "warmup_es_min.pdf"
    asset.write_bytes(b"%PDF-1.4\n% dummy\n")
    monkeypatch.setattr(W, "get_warmup_asset_path", lambda: asset)

    # Ejecutar
    status = await W.run_warmup_once()
    # Debe marcarse como completado y “listo”
    assert hasattr(status, "is_ready")
    assert status.is_ready is True
# Fin del archivo