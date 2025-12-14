# -*- coding: utf-8 -*-
"""
Tests del dataclass WarmupStatus: valores por defecto y lógica de is_ready.
"""

import importlib


def test_warmup_status_defaults_and_collections():
    ws_mod = importlib.import_module("app.shared.core.warmup_status_cache")
    WarmupStatus = ws_mod.WarmupStatus

    s = WarmupStatus()
    # Defaults temporales
    assert s.started_at is None
    assert s.ended_at is None
    assert s.duration_sec is None

    # Flags por defecto (según diseño)
    assert s.fast_ok is False
    assert s.hires_ok is False
    assert s.table_model_ok is False
    assert s.http_client_ok is False
    assert s.http_health_ok is False
    # Asunción por defecto tesseract_ok True y el resto False
    assert s.tesseract_ok is True
    assert s.ghostscript_ok is False
    assert s.ghostscript_path is None
    assert s.poppler_ok is False
    assert s.poppler_path is None
    assert s.http_health_latency_ms is None

    # Colecciones deben iniciar vacías y ser listas diferentes por instancia
    assert isinstance(s.errors, list) and s.errors == []
    assert isinstance(s.warnings, list) and s.warnings == []
    s2 = WarmupStatus()
    assert s.errors is not s2.errors
    assert s.warnings is not s2.warnings


def test_is_ready_requires_fast_and_http_client():
    ws_mod = importlib.import_module("app.shared.core.warmup_status_cache")
    WarmupStatus = ws_mod.WarmupStatus

    s = WarmupStatus()
    # Nada listo al inicio
    assert s.is_ready is False

    # Solo fast_ok -> aún no listo
    s.fast_ok = True
    assert s.is_ready is False

    # Solo http_client_ok -> aún no listo
    s.fast_ok = False
    s.http_client_ok = True
    assert s.is_ready is False

    # Ambos True -> listo
    s.fast_ok = True
    s.http_client_ok = True
    assert s.is_ready is True
# Fin del archivo