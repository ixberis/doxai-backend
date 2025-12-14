
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/routes/test_routes_rag.py

Pruebas de contrato para los ruteadores del módulo RAG Fase 1.

En lugar de invocar directamente la base de datos, estas pruebas se
centran en verificar que las rutas clave estén registradas en la app
FastAPI, con los paths y métodos HTTP esperados.

Se valida la existencia de:
- /rag/indexing/jobs [POST, GET]
- /rag/indexing/jobs/{job_id}/progress [GET]
- /rag/indexing/reindex/document/{file_id} [POST]
- /rag/status/documents... y /rag/status/projects...
- /rag/ocr/callbacks/azure [POST], /rag/ocr/summary [GET], /rag/ocr/health [GET]
- /rag/diagnostics/pipeline-efficiency [GET], /rag/diagnostics/ocr-backlog [GET]
- /rag/metrics/prometheus [GET], /rag/metrics/snapshot/db [GET],
  /rag/metrics/snapshot/memory [GET]

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from fastapi.routing import APIRoute

from app.main import app


def _find_route(path: str, method: str) -> APIRoute | None:
    """Busca una ruta por path exacto y método HTTP."""
    for route in app.routes:
        if isinstance(route, APIRoute):
            if route.path == path and method in route.methods:
                return route
    return None


def test_indexing_routes_exist():
    """Las rutas principales de indexación deben existir."""
    assert _find_route("/rag/projects/{project_id}/jobs/indexing", "POST") is not None
    assert _find_route("/rag/jobs/{job_id}/progress", "GET") is not None
    assert _find_route("/rag/projects/{project_id}/jobs", "GET") is not None
    # Reindex routes
    assert _find_route("/rag/indexing/reindex/project/{project_id}", "POST") is not None


def test_status_routes_exist():
    """Las rutas de estado RAG (documentos y proyectos) deben existir."""
    assert _find_route("/rag/documents/{file_id}/status", "GET") is not None
    assert _find_route("/rag/status/projects", "GET") is not None
    assert _find_route("/rag/status/projects/{project_id}", "GET") is not None


def test_ocr_routes_exist():
    """Las rutas de OCR (callbacks y admin) deben existir."""
    assert _find_route("/rag/ocr/callbacks/azure", "POST") is not None
    assert _find_route("/rag/ocr/summary", "GET") is not None
    assert _find_route("/rag/ocr/health", "GET") is not None


def test_diagnostics_routes_exist():
    """Las rutas de diagnóstico deben existir."""
    assert (
        _find_route("/rag/diagnostics/pipeline-efficiency", "GET") is not None
    )
    assert _find_route("/rag/diagnostics/ocr-backlog", "GET") is not None


def test_metrics_routes_exist():
    """Las rutas de métricas deben existir."""
    assert _find_route("/rag/metrics/prometheus", "GET") is not None
    assert _find_route("/rag/metrics/snapshot/db", "GET") is not None
    assert _find_route("/rag/metrics/snapshot/memory", "GET") is not None


# Fin del archivo backend/tests/modules/rag/routes/test_routes_rag.py
