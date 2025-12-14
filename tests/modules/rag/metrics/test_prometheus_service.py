
# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/metrics/test_prometheus_service.py

Pruebas de humo (smoke tests) para RagPrometheusMetricsService.

Se valida que:
- update_from_snapshot(snapshot) no lance excepciones al alimentar los
  collectors de pipeline, OCR y embeddings con un snapshot mínimo.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from app.modules.rag.metrics.schemas.snapshot_schemas import (
    RagMetricsDbSnapshot,
)
from app.modules.rag.metrics.services.prometheus_service import (
    RagPrometheusMetricsService,
)


def test_prometheus_update_from_empty_snapshot_does_not_fail():
    """
    Un snapshot vacío debe poder alimentar los collectors sin provocar
    errores (útil como smoke test).
    """
    empty_snapshot = RagMetricsDbSnapshot(
        document_readiness=[],
        pipeline_latency=[],
        ocr_costs_daily=[],
        embedding_volume=[],
        embedding_coverage=[],
    )

    # No debe lanzar excepción
    RagPrometheusMetricsService.update_from_snapshot(empty_snapshot)


# Fin del archivo backend/tests/modules/rag/metrics/test_prometheus_service.py
