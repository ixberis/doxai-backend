
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/facades/test_convert_facade_contracts.py

Pruebas de contrato para el facade de conversión a texto (sin OCR).

Se valida:
- La función convert_to_text existe y es async.
- La firma expone parámetros esperados para orquestar la conversión.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

import inspect
from uuid import uuid4

import pytest

from app.modules.rag.facades.convert_facade import convert_to_text, ConvertedText

def test_convert_to_text_is_coroutine():
    """Verificar que convert_to_text es una corrutina async."""
    assert inspect.iscoroutinefunction(convert_to_text)

def test_convert_to_text_signature_minimal():
    """
    Validar que la firma de convert_to_text contenga parámetros clave.
    No se fuerza el orden exacto, solo la presencia semántica.
    """
    sig = inspect.signature(convert_to_text)
    params = set(sig.parameters.keys())
    
    # Contrato mínimo alineado con v2 (file_id en lugar de document_file_id)
    expected_subset = {"db", "file_id"}
    missing = expected_subset - params
    assert not missing, f"convert_to_text requiere parámetros {missing}"

@pytest.mark.asyncio
async def test_convert_to_text_currently_not_implemented():
    """Verificar que PDF aún lanza NotImplementedError."""
    # Mock simple de storage_client para que la validación pase
    class MockStorageClient:
        async def read(self, uri: str) -> bytes:
            return b"fake pdf content"
        async def write(self, uri: str, data: bytes, content_type: str):
            pass
    
    with pytest.raises(NotImplementedError):
        await convert_to_text(
            db=None,
            job_id=uuid4(),
            file_id=uuid4(),
            source_uri="supabase://bucket/file.pdf",
            mime_type="application/pdf",
            storage_client=MockStorageClient(),
        )

def test_converted_text_dataclass_fields():
    fields = {f.name for f in ConvertedText.__dataclass_fields__.values()}
    assert {"result_uri", "byte_size", "checksum"} <= fields
# Fin del archivo
