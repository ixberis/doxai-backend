
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/models/test_document_embedding_model.py

Pruebas de contrato para el modelo DocumentEmbedding del módulo RAG.

Se valida:
- Nombre de tabla.
- Presencia de columnas clave.
- Existencia de constraint de unicidad por documento+chunk+modelo.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from sqlalchemy import UniqueConstraint

from app.modules.rag.models.embedding_models import DocumentEmbedding


def test_document_embedding_tablename():
    """El nombre de la tabla debe coincidir con el script SQL."""
    assert DocumentEmbedding.__tablename__ == "document_embeddings"


def test_document_embedding_columns_exist():
    """El modelo debe exponer las columnas principales."""
    cols = DocumentEmbedding.__table__.c
    expected = {
        "embedding_id",
        "file_id",
        "chunk_id",
        "chunk_index",
        "embedding_model",
        "embedding_vector",
        "is_active",
        "created_at",
    }
    missing = expected - set(cols.keys())
    assert not missing, f"Faltan columnas en DocumentEmbedding: {missing}"


def test_document_embedding_unique_constraint():
    """
    Debe existir un constraint de unicidad para
    (file_id, chunk_index, embedding_model) que garantiza idempotencia.
    """
    constraints = {
        tuple(c.columns.keys())
        for c in DocumentEmbedding.__table__.constraints
        if isinstance(c, UniqueConstraint)
    }
    expected = ("file_id", "chunk_index", "embedding_model")
    assert expected in constraints


# Fin del archivo backend/tests/modules/rag/models/test_document_embedding_model.py
