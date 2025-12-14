
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_facades_exports.py

Pruebas de contrato para el paquete de facades del módulo RAG.
Se valida que el módulo `app.modules.rag.facades` exponga las funciones
clave del pipeline de indexación:

- convert_to_text
- run_ocr
- chunk_text
- generate_embeddings
- integrate_vector_index
- run_indexing_job

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

import inspect

from app.modules.rag import facades as rag_facades


def test_facades_export_surface():
    """El paquete facades debe exponer explícitamente las funciones esperadas."""
    expected = {
        "convert_to_text",
        "run_ocr",
        "chunk_text",
        "generate_embeddings",
        "integrate_vector_index",
        "run_indexing_job",
    }

    exported = set(getattr(rag_facades, "__all__", []))
    # Si no existe __all__, caemos al dir() como fallback.
    if not exported:
        exported = {name for name in dir(rag_facades) if not name.startswith("_")}

    missing = expected - exported
    assert not missing, f"Faltan facades esperados en rag.facades: {missing}"

    # Todas las funciones esperadas deben ser callables
    for name in expected:
        obj = getattr(rag_facades, name, None)
        assert callable(obj), f"{name} debe ser callable"


def test_run_indexing_job_is_coroutine():
    """run_indexing_job debe ser una corrutina (async)."""
    func = getattr(rag_facades, "run_indexing_job", None)
    assert func is not None
    assert inspect.iscoroutinefunction(func)


# Fin del archivo backend/tests/modules/rag/facades/test_facades_exports.py
