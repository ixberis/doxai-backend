# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/enums/test_rag_enums.py

Pruebas de contrato para los enums del módulo RAG:
- RagPhase
- RagJobPhase
- OcrOptimization
- InputProcessingStatus

Se valida:
- Exportación correcta desde los módulos.
- Conjunto de valores esperados.
- Compatibilidad básica de tipos (StrEnum).

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from enum import Enum

from app.modules.rag.enums import RagPhase, RagJobPhase, OcrOptimization, InputProcessingStatus


def test_rag_phase_values():
    """RagPhase debe contener todas las fases del pipeline RAG Fase 1."""
    values = {p.value for p in RagPhase}
    assert {"convert", "ocr", "chunk", "embed", "integrate", "ready"} == values


def test_rag_job_phase_values():
    """RagJobPhase debe expresar el estado macro del job."""
    values = {p.value for p in RagJobPhase}
    assert {"queued", "running", "completed", "failed", "cancelled"} == values


def test_ocr_optimization_values():
    """OcrOptimization debe tener las tres estrategias definidas."""
    values = {o.value for o in OcrOptimization}
    assert {"fast", "accurate", "balanced"} == values


def test_input_processing_status_values():
    """InputProcessingStatus debe usar valores canónicos en minúsculas."""
    values = {s.value for s in InputProcessingStatus}
    # Valores canónicos del pipeline (minúsculas)
    expected_canonical = {"uploaded", "queued", "processing", "parsed", "vectorized", "failed"}
    assert expected_canonical == values
    
    # Verificar que aliases funcionan (apuntan a valores canónicos)
    assert InputProcessingStatus.pending == InputProcessingStatus.queued
    assert InputProcessingStatus.completed == InputProcessingStatus.parsed
    
    # Asegurar que el enum es hijo de Enum
    from enum import Enum
    assert issubclass(InputProcessingStatus, Enum)


# Fin del archivo backend/tests/modules/rag/enums/test_rag_enums.py
