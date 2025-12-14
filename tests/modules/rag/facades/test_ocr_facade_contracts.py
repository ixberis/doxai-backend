
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_ocr_facade_contracts.py

Pruebas de contrato para el facade de OCR del módulo RAG.

Se valida:
- La función run_ocr existe y es async.
- La firma incluye parámetros para controlar:
    * db
    * file_id
    * needs_ocr / optimization

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

import inspect

from app.modules.rag.facades.ocr_facade import run_ocr


def test_run_ocr_is_coroutine():
    """run_ocr debe ser una corrutina (async)."""
    assert inspect.iscoroutinefunction(run_ocr)


def test_run_ocr_signature_minimal():
    """La firma de run_ocr debe exponer los parámetros esenciales alineados con v2."""
    sig = inspect.signature(run_ocr)
    params = set(sig.parameters.keys())
    expected = {"db", "file_id"}
    missing = expected - params
    assert not missing, f"run_ocr requiere parámetros {missing}"


# Fin del archivo backend/tests/modules/rag/facades/test_ocr_facade_contracts.py
