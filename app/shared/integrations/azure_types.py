# -*- coding: utf-8 -*-
"""
backend/app/shared/integrations/azure_types.py

Tipos y estructuras para Azure Document Intelligence.
Define los tipos de datos genéricos para la integración con Azure Cognitive Services.

IMPORTANTE: Este módulo NO debe importar nada de app.modules.* para evitar ciclos.

Author: DoxAI
Date: 2025-11-28
"""

from typing import TypedDict, List, Optional, Dict, Any
from enum import Enum


class AzureAnalysisStatus(str, Enum):
    """Estados posibles del análisis en Azure"""
    NOT_STARTED = "notStarted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class AzureModelId(str, Enum):
    """Modelos disponibles en Azure Document Intelligence"""
    PREBUILT_READ = "prebuilt-read"  # Solo lectura de texto
    PREBUILT_LAYOUT = "prebuilt-layout"  # Layout + tablas + estructura
    PREBUILT_DOCUMENT = "prebuilt-document"  # Documento general con KV pairs
    PREBUILT_INVOICE = "prebuilt-invoice"  # Facturas
    PREBUILT_RECEIPT = "prebuilt-receipt"  # Recibos


class AzureBoundingBox(TypedDict, total=False):
    """Coordenadas de un área rectangular en el documento"""
    x: float
    y: float
    width: float
    height: float


class AzureSpan(TypedDict):
    """Rango de caracteres en el contenido extraído"""
    offset: int
    length: int


class AzureWord(TypedDict, total=False):
    """Palabra individual extraída"""
    content: str
    polygon: List[float]  # 8 valores: x1,y1,x2,y2,x3,y3,x4,y4
    span: AzureSpan
    confidence: float


class AzureLine(TypedDict, total=False):
    """Línea de texto extraída"""
    content: str
    polygon: List[float]
    spans: List[AzureSpan]


class AzureParagraph(TypedDict, total=False):
    """Párrafo extraído con roles (título, texto, etc.)"""
    content: str
    role: Optional[str]  # "title", "sectionHeading", "pageHeader", etc.
    bounding_regions: List[Dict[str, Any]]
    spans: List[AzureSpan]


class AzureTableCell(TypedDict, total=False):
    """Celda individual de una tabla"""
    row_index: int
    column_index: int
    row_span: int
    column_span: int
    content: str
    bounding_regions: List[Dict[str, Any]]
    spans: List[AzureSpan]
    kind: Optional[str]  # "columnHeader", "rowHeader", "content", etc.


class AzureTable(TypedDict, total=False):
    """Tabla extraída del documento"""
    row_count: int
    column_count: int
    cells: List[AzureTableCell]
    bounding_regions: List[Dict[str, Any]]
    spans: List[AzureSpan]


class AzureKeyValuePair(TypedDict, total=False):
    """Par clave-valor extraído (ej: "Nombre: Juan")"""
    key: Dict[str, Any]
    value: Dict[str, Any]
    confidence: float


class AzurePage(TypedDict, total=False):
    """Página individual del documento analizado"""
    page_number: int
    angle: float
    width: float
    height: float
    unit: str  # "pixel" o "inch"
    words: List[AzureWord]
    lines: List[AzureLine]
    spans: List[AzureSpan]


class AzureDocumentResult(TypedDict, total=False):
    """Resultado completo del análisis de Azure Document Intelligence"""
    status: str  # AzureAnalysisStatus
    created_date_time: str
    last_updated_date_time: str
    analyze_result: Dict[str, Any]  # Contiene pages, paragraphs, tables, etc.


class AzureAnalyzeResponse(TypedDict):
    """Respuesta del endpoint de análisis (inicio del job)"""
    operation_location: str  # URL para consultar el estado
    request_id: str


class AzureErrorResponse(TypedDict):
    """Respuesta de error de Azure"""
    error: Dict[str, Any]  # code, message, details


# Tipos de respuesta simplificados para uso interno
class ConvertedDocument(TypedDict, total=False):
    """Documento convertido en formato interno unificado"""
    text: str
    pages: List[Dict[str, Any]]
    paragraphs: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    source: str  # "azure_document_intelligence"
    model_used: str  # Ej: "prebuilt-layout"


class AzureConfig(TypedDict, total=False):
    """Configuración para el cliente de Azure"""
    endpoint: str  # Ej: "https://<resource>.cognitiveservices.azure.com/"
    api_key: str
    api_version: str  # Ej: "2024-07-31-preview"
    default_model: str  # Modelo por defecto a usar
    timeout_sec: int
    max_retries: int


# Export all types
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
