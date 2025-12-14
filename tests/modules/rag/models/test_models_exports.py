
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/models/test_models_exports.py

Pruebas de contrato para la superficie de exportación del paquete de
modelos del módulo RAG.

Se valida que el paquete `app.modules.rag.models` exponga:

- ChunkMetadata
- DocumentEmbedding
- RagJob
- RagJobEvent

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from app.modules.rag import models as rag_models


def test_models_export_surface():
    """El paquete models debe exponer las clases principales."""
    names = getattr(rag_models, "__all__", [])
    exported = set(names) if names else {n for n in dir(rag_models) if not n.startswith("_")}

    expected = {"ChunkMetadata", "DocumentEmbedding", "RagJob", "RagJobEvent"}
    missing = expected - exported
    assert not missing, f"Faltan modelos en app.modules.rag.models: {missing}"

    for name in expected:
        obj = getattr(rag_models, name, None)
        assert obj is not None
        assert isinstance(obj, type)


# Fin del archivo backend/tests/modules/rag/models/test_models_exports.py
