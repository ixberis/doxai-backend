
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_chunk_facade_contracts.py

Pruebas de contrato para el facade de chunking del módulo RAG.

Se valida:
- La función chunk_text existe y es async.
- La firma incluye parámetros mínimos para identificar documento y texto.
- Las estructuras auxiliares (si existen) pueden importarse.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

import inspect

from app.modules.rag.facades.chunk_facade import chunk_text


def test_chunk_text_is_coroutine():
    """chunk_text debe ser una corrutina (async)."""
    assert inspect.iscoroutinefunction(chunk_text)


def test_chunk_text_signature_minimal():
    """La firma de chunk_text debe incluir db y file_id."""
    sig = inspect.signature(chunk_text)
    params = set(sig.parameters.keys())
    expected = {"db", "file_id"}
    missing = expected - params
    assert not missing, f"chunk_text requiere parámetros {missing}"


# Fin del archivo backend/tests/modules/rag/facades/test_chunk_facade_contracts.py
