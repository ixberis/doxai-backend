# -*- coding: utf-8 -*-
"""
Verifica que app.shared.core (paquete) exponga los símbolos públicos esperados
y que el mecanismo de re-export funcione aun si el módulo fuente cambia.
"""

import types
import importlib
import pytest


EXPECTED_EXPORTS = {
    "run_warmup_once",
    "get_warmup_status",
    "shutdown_all",
    "get_http_client",
    "retry_with_backoff",
    "retry_get_with_backoff",
    "retry_post_with_backoff",
    "warmup_unstructured",
    "ensure_table_model_loaded",
    "get_table_agent",
    "get_fast_parser",
    "get_standard_language_config",
}


def test_public_api_contains_expected_symbols():
    # Carga normal del paquete
    core = importlib.import_module("app.shared.core")
    # __all__ existe y contiene lo declarado
    assert hasattr(core, "__all__")
    exported = set(core.__all__)
    # Debe contener al menos los símbolos esperados (puede tener más)
    missing = EXPECTED_EXPORTS - exported
    assert not missing, f"Faltan exports en __all__: {missing}"
    # Y cada símbolo debe estar accesible como atributo
    for name in EXPECTED_EXPORTS:
        assert hasattr(core, name), f"No está accesible core.{name}"


def test_reexport_binds_from_resource_cache(monkeypatch):
    """
    Simula un 'resource_cache' con funciones dummy y verifica que el paquete
    re-exporte los nombres desde allí en la importación.
    """
    # Construimos un falso módulo source para los re-exports
    fake = types.SimpleNamespace(
        run_warmup_once=lambda: "run_warmup_once",
        get_warmup_status=lambda: "get_warmup_status",
        shutdown_all=lambda: "shutdown_all",
        get_http_client=lambda: "get_http_client",
        retry_with_backoff=lambda: "retry_with_backoff",
        retry_get_with_backoff=lambda: "retry_get_with_backoff",
        retry_post_with_backoff=lambda: "retry_post_with_backoff",
        warmup_unstructured=lambda: "warmup_unstructured",
        ensure_table_model_loaded=lambda: "ensure_table_model_loaded",
        get_table_agent=lambda: "get_table_agent",
        get_fast_parser=lambda: "get_fast_parser",
        get_standard_language_config=lambda: "get_standard_language_config",
    )

    # Inyectamos el fake ANTES de recargar el paquete
    monkeypatch.setitem(
        __import__("sys").modules, "app.shared.core.resource_cache", fake
    )

    # Importamos y recargamos el paquete para que tome el fake
    core = importlib.import_module("app.shared.core")
    importlib.reload(core)

    # Ahora cada símbolo debe resolver al callable del fake
    for name in EXPECTED_EXPORTS:
        assert getattr(core, name)() == name, f"Re-export incorrecto: {name}"
# Fin del archivo