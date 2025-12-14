# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/__init__.py

Clientes de integración con servicios externos.
"""

from .azure_document_intelligence import AzureDocumentIntelligenceClient, AzureOcrResult
from .openai_embeddings_client import generate_embeddings
from .azure_types import (
    AzureAnalysisStatus,
    AzureModelId,
    AzureDocumentResult,
    AzurePage,
    AzureConfig,
)

__all__ = [
    "AzureDocumentIntelligenceClient",
    "AzureOcrResult",
    "generate_embeddings",
    "AzureAnalysisStatus",
    "AzureModelId",
    "AzureDocumentResult",
    "AzurePage",
    "AzureConfig",
]
