
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/collectors/ocr_collector.py

Collector de métricas Prometheus para el subsistema de OCR del módulo RAG.
Se alimenta de los KPIs agregados en base de datos (vw_ocr_request_summary
y las vistas materializadas derivadas) para exponer:

- Volumen de requests por día, proveedor y modelo.
- Páginas y caracteres procesados.
- Reintentos acumulados (retries).
- Costos diarios en USD, desglosados por proveedor/modelo/optimización.

Métricas expuestas (sugeridas):
- rag_ocr_requests_total{completed_date,provider,provider_model,ocr_optimization}
- rag_ocr_pages_total{completed_date,provider,provider_model,ocr_optimization}
- rag_ocr_characters_total{completed_date,provider,provider_model,ocr_optimization}
- rag_ocr_retries_total{completed_date,provider,provider_model,ocr_optimization}
- rag_ocr_cost_usd_total{completed_date,provider,provider_model,ocr_optimization}

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from prometheus_client import Gauge

from app.modules.rag.metrics.schemas.snapshot_schemas import (
    RagMetricsDbSnapshot,
    RagOcrCostsDailyKpi,
)

# ============================================================================
# Definición de métricas Prometheus para OCR
# ============================================================================

OCR_REQUESTS_TOTAL = Gauge(
    "rag_ocr_requests_total",
    "Número total de requests OCR por día, proveedor, modelo y estrategia.",
    labelnames=("completed_date", "provider", "provider_model", "ocr_optimization"),
)

OCR_PAGES_TOTAL = Gauge(
    "rag_ocr_pages_total",
    "Número total de páginas procesadas por OCR por día, proveedor, modelo y estrategia.",
    labelnames=("completed_date", "provider", "provider_model", "ocr_optimization"),
)

OCR_CHARACTERS_TOTAL = Gauge(
    "rag_ocr_characters_total",
    "Número total de caracteres procesados por OCR por día, proveedor, modelo y estrategia.",
    labelnames=("completed_date", "provider", "provider_model", "ocr_optimization"),
)

OCR_RETRIES_TOTAL = Gauge(
    "rag_ocr_retries_total",
    "Número total de reintentos de OCR por día, proveedor, modelo y estrategia.",
    labelnames=("completed_date", "provider", "provider_model", "ocr_optimization"),
)

OCR_COST_USD_TOTAL = Gauge(
    "rag_ocr_cost_usd_total",
    "Costo total diario de OCR en USD por día, proveedor, modelo y estrategia.",
    labelnames=("completed_date", "provider", "provider_model", "ocr_optimization"),
)


# ============================================================================
# Collector
# ============================================================================


class RagOcrMetricsCollector:
    """
    Encapsula la lógica para mapear los KPIs de OCR del módulo RAG a métricas
    Prometheus.

    Uso típico:
        snapshot = RagMetricsService.get_db_snapshot(db)
        RagOcrMetricsCollector.update_from_snapshot(snapshot)
    """

    @classmethod
    def _update_ocr_costs_daily(
        cls,
        ocr_items: list[RagOcrCostsDailyKpi],
    ) -> None:
        """
        Actualiza métricas derivadas de la vista kpis.mv_rag_ocr_costs_daily.
        """
        OCR_REQUESTS_TOTAL.clear()
        OCR_PAGES_TOTAL.clear()
        OCR_CHARACTERS_TOTAL.clear()
        OCR_RETRIES_TOTAL.clear()
        OCR_COST_USD_TOTAL.clear()

        for item in ocr_items:
            completed_date_str = item.completed_date.isoformat()
            labels = dict(
                completed_date=completed_date_str,
                provider=item.provider,
                provider_model=item.provider_model,
                ocr_optimization=item.ocr_optimization,
            )

            OCR_REQUESTS_TOTAL.labels(**labels).set(float(item.requests_total))
            OCR_PAGES_TOTAL.labels(**labels).set(float(item.pages_total))
            OCR_CHARACTERS_TOTAL.labels(**labels).set(float(item.characters_total))
            OCR_RETRIES_TOTAL.labels(**labels).set(float(item.retries_total))
            OCR_COST_USD_TOTAL.labels(**labels).set(float(item.cost_total_usd))

    @classmethod
    def update_from_snapshot(cls, snapshot: RagMetricsDbSnapshot) -> None:
        """
        Punto de entrada principal: recibe un RagMetricsDbSnapshot y actualiza
        las métricas relacionadas con OCR.
        """
        cls._update_ocr_costs_daily(snapshot.ocr_costs_daily)


# Fin del archivo backend/app/modules/rag/metrics/collectors/ocr_collector.py
