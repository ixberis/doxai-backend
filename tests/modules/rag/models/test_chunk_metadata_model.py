
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/models/test_chunk_metadata_model.py

Pruebas de contrato para el modelo ChunkMetadata del módulo RAG.

Se valida:
- Nombre de tabla.
- Presencia de columnas clave (chunk_index, bounds de página, etc.).

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from app.modules.rag.models.chunk_models import ChunkMetadata


def test_chunk_metadata_tablename():
    """El nombre de la tabla debe coincidir con el script SQL."""
    assert ChunkMetadata.__tablename__ == "chunk_metadata"


def test_chunk_metadata_columns_exist():
    """El modelo debe exponer las columnas principales."""
    cols = ChunkMetadata.__table__.c
    expected = {
        "chunk_id",
        "file_id",
        "chunk_index",
        "source_page_start",
        "source_page_end",
        "token_count",
        "created_at",
    }
    missing = expected - set(cols.keys())
    assert not missing, f"Faltan columnas en ChunkMetadata: {missing}"


# Fin del archivo backend/tests/modules/rag/models/test_chunk_metadata_model.py
