
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/models/test_job_models.py

Pruebas de contrato para los modelos de jobs del módulo RAG:

- RagJob
- RagJobEvent

Se valida:
- Nombre de tabla.
- Columnas básicas de identificación y estado.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from app.modules.rag.models.job_models import RagJob, RagJobEvent


def test_rag_job_tablename_and_columns():
    """Validar tabla rag_jobs y columnas clave."""
    assert RagJob.__tablename__ == "rag_jobs"
    cols = RagJob.__table__.c
    expected = {
        "job_id",
        "project_id",
        "file_id",
        "status",
        "phase_current",
        "started_at",
        "created_at",
        "updated_at",
        "created_by",
        "completed_at",
        "failed_at",
        "cancelled_at",
    }
    missing = expected - set(cols.keys())
    assert not missing, f"Faltan columnas en RagJob: {missing}"


def test_rag_job_event_tablename_and_columns():
    """Validar tabla rag_job_events y columnas clave."""
    assert RagJobEvent.__tablename__ == "rag_job_events"
    cols = RagJobEvent.__table__.c
    expected = {
        "job_event_id",
        "job_id",
        "event_type",
        "rag_phase",
        "progress_pct",
        "message",
        "event_payload",
        "created_at",
    }
    missing = expected - set(cols.keys())
    assert not missing, f"Faltan columnas en RagJobEvent: {missing}"


# Fin del archivo backend/tests/modules/rag/models/test_job_models.py
