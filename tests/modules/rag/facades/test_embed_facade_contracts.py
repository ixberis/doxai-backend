
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_embed_facade_contracts.py

Pruebas de contrato para el facade de generación de embeddings.

Se valida:
- La función generate_embeddings existe y es async.
- La firma expone parámetros mínimos esperados:
    * db
    * file_id
    * embedding_model (opcional pero recomendado)

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

import inspect

from app.modules.rag.facades.embed_facade import generate_embeddings


def test_generate_embeddings_is_coroutine():
    """generate_embeddings debe ser una corrutina (async)."""
    assert inspect.iscoroutinefunction(generate_embeddings)


def test_generate_embeddings_signature_minimal():
    """La firma de generate_embeddings debe exponer parámetros clave."""
    sig = inspect.signature(generate_embeddings)
    params = set(sig.parameters.keys())
    expected_subset = {"db", "file_id"}
    missing = expected_subset - params
    assert not missing, f"generate_embeddings requiere parámetros {missing}"


# Fin del archivo backend/tests/modules/rag/facades/test_embed_facade_contracts.py
