
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_integrate_facade_contracts.py

Pruebas de contrato para el facade de integración de embeddings en el
vector index.

Se valida:
- La función integrate_vector_index existe y es async.
- La firma expone parámetros mínimos para identificar documento y contexto
  de integración.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

import inspect

from app.modules.rag.facades.integrate_facade import integrate_vector_index


def test_integrate_vector_index_is_coroutine():
    """integrate_vector_index debe ser una corrutina (async)."""
    assert inspect.iscoroutinefunction(integrate_vector_index)


def test_integrate_vector_index_signature_minimal():
    """La firma de integrate_vector_index debe incluir db y file_id."""
    sig = inspect.signature(integrate_vector_index)
    params = set(sig.parameters.keys())
    expected = {"db", "file_id"}
    missing = expected - params
    assert not missing, f"integrate_vector_index requiere parámetros {missing}"


# Fin del archivo backend/tests/modules/rag/facades/test_integrate_facade_contracts.py
