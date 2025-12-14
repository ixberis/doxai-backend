
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/schemas/test_schemas_imports_and_fields.py

Pruebas de contrato para los esquemas Pydantic del módulo RAG relacionados
con jobs de indexación.

Se valida:
- Importación de IndexingJobCreate, IndexingJobResponse,
  JobProgressResponse y JobProgressEvent.
- Presencia de campos clave en los modelos.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from app.modules.rag.schemas.indexing_schemas import (
    IndexingJobCreate,
    IndexingJobResponse,
    JobProgressResponse,
    JobProgressEvent,
)


def _get_fields(model) -> set[str]:
    """Helper robusto para Pydantic v1/v2."""
    if hasattr(model, "model_fields"):  # Pydantic v2
        return set(model.model_fields.keys())
    if hasattr(model, "__fields__"):  # Pydantic v1
        return set(model.__fields__.keys())
    return set()


def test_indexing_job_create_fields():
    """IndexingJobCreate debe exponer campos mínimos esperados."""
    fields = _get_fields(IndexingJobCreate)
    expected_subset = {"file_id", "project_id", "needs_ocr"}
    missing = expected_subset - fields
    assert not missing, f"Faltan campos en IndexingJobCreate: {missing}"


def test_indexing_job_response_fields():
    """IndexingJobResponse debe incluir identificadores y estado del job."""
    fields = _get_fields(IndexingJobResponse)
    expected_subset = {"job_id", "phase", "project_id"}
    missing = expected_subset - fields
    assert not missing, f"Faltan campos en IndexingJobResponse: {missing}"


def test_job_progress_response_fields():
    """JobProgressResponse debe incorporar progreso y timeline."""
    fields = _get_fields(JobProgressResponse)
    expected_subset = {"job_id", "file_id", "phase", "timeline", "progress_pct"}
    missing = expected_subset - fields
    assert not missing, f"Faltan campos en JobProgressResponse: {missing}"


def test_job_progress_event_fields():
    """JobProgressEvent debe describir un evento dentro del pipeline."""
    fields = _get_fields(JobProgressEvent)
    expected_subset = {"phase", "created_at"}
    missing = expected_subset - fields
    assert not missing, f"Faltan campos en JobProgressEvent: {missing}"


# Fin del archivo backend/tests/modules/rag/schemas/test_schemas_imports_and_fields.py
