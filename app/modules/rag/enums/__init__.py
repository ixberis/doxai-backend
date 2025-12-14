
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/enums

Inicializador del paquete de enumeraciones RAG Fase 1.
Reexporta enums públicos para facilitar imports en módulos superiores.

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""

# Importar desde módulo Files los ENUMs compartidos
from app.modules.files.enums import (
    FileCategory,
    FileCategoryType,
    file_category_as_pg_enum,
    InputProcessingStatus,
    input_processing_status_as_pg_enum,
)

from .ocr_optimization_enum import OcrOptimization, as_pg_enum as ocr_optimization_as_pg_enum
from .rag_phase_enum import (
    RagPhase,
    RagPhaseType,
    RagJobPhase,
    RagJobPhaseType,
    as_pg_enum as rag_phase_as_pg_enum,
    rag_job_phase_as_pg_enum,
)

__all__ = [
    "FileCategory",
    "FileCategoryType",
    "file_category_as_pg_enum",
    "InputProcessingStatus",
    "input_processing_status_as_pg_enum",
    "OcrOptimization",
    "ocr_optimization_as_pg_enum",
    "RagPhase",
    "RagPhaseType",
    "RagJobPhase",
    "RagJobPhaseType",
    "rag_phase_as_pg_enum",
    "rag_job_phase_as_pg_enum",
]
# Fin del archivo backend\app\modules\rag\enums\__init__.py