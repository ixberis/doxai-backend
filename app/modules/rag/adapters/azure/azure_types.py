# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/adapters/azure/azure_types.py

DEPRECATED: Este módulo ya no se usa.
Los tipos genéricos de Azure ahora viven en:
    app.shared.integrations.azure_types

Este archivo se mantiene temporalmente para compatibilidad hacia atrás,
pero simplemente re-exporta desde shared.integrations.

Author: DoxAI
Date: 2025-11-28 (DEPRECATED)
"""

# Re-exportar desde shared.integrations para compatibilidad
from app.shared.integrations.azure_types import (
    AzureAnalysisStatus,
    AzureModelId,
    AzureBoundingBox,
    AzureSpan,
    AzureWord,
    AzureLine,
    AzureParagraph,
    AzureTableCell,
    AzureTable,
    AzureKeyValuePair,
    AzurePage,
    AzureDocumentResult,
    AzureAnalyzeResponse,
    AzureErrorResponse,
    ConvertedDocument,
    AzureConfig,
)

__all__ = [
    'AzureAnalysisStatus',
    'AzureModelId',
    'AzureBoundingBox',
    'AzureSpan',
    'AzureWord',
    'AzureLine',
    'AzureParagraph',
    'AzureTableCell',
    'AzureTable',
    'AzureKeyValuePair',
    'AzurePage',
    'AzureDocumentResult',
    'AzureAnalyzeResponse',
    'AzureErrorResponse',
    'ConvertedDocument',
    'AzureConfig',
]
