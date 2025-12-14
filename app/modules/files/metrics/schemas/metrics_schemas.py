
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/schemas/metrics_schemas.py

TypedDicts para estructurar el snapshot de métricas del módulo Files (Files v2).

El snapshot tiene la forma::

    {
        "inputs": {
            "overview": {"total_files": int, "total_bytes": int},
            "status": [{"status": str, "count": int}, ...],
            "daily_created": [("YYYY-MM-DD", int), ...],
        },
        "products": {
            "overview": {"total_files": int, "total_bytes": int},
            "by_type": [{"type": str, "count": int}, ...],
            "daily_generated": [("YYYY-MM-DD", int), ...],
        },
        "activity": {
            "totals": {"<event_name>": int, ...},
            "downloads_daily": [("YYYY-MM-DD", int), ...],
            "generated_daily": [("YYYY-MM-DD", int), ...],
        },
    }

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""
from __future__ import annotations

from typing import Dict, List, Tuple, TypedDict


# ---------------------------------------------------------------------------
# Overviews
# ---------------------------------------------------------------------------


class InputsOverview(TypedDict, total=False):
    """
    Resumen de archivos insumo para un proyecto.

    Claves:
        - total_files: número de archivos insumo.
        - total_bytes: tamaño total en bytes.
    """
    total_files: int
    total_bytes: int


class ProductsOverview(TypedDict, total=False):
    """
    Resumen de archivos producto para un proyecto.

    Claves:
        - total_files: número de archivos producto.
        - total_bytes: tamaño total en bytes.
    """
    total_files: int
    total_bytes: int


# ---------------------------------------------------------------------------
# Entradas auxiliares
# ---------------------------------------------------------------------------


class StatusEntry(TypedDict, total=False):
    """
    Entrada de conteo por estado de procesamiento de insumos.
    """
    status: str
    count: int


class TypeEntry(TypedDict, total=False):
    """
    Entrada de conteo por tipo lógico de archivo producto.
    """
    type: str
    count: int


# Serie diaria representada como (fecha_iso, valor)
DailySeriesEntry = Tuple[str, int]


class ActivityTotals(TypedDict, total=False):
    """
    Totales de actividad por tipo de evento.

    Se deja abierto para permitir llaves dinámicas, por ejemplo:
        {"downloaded": 12, "generated": 3, ...}
    """
    # Dict[str, int] abierto; TypedDict vacío indica mapa flexible
    pass


# ---------------------------------------------------------------------------
# Secciones del snapshot
# ---------------------------------------------------------------------------


class InputsSection(TypedDict, total=False):
    overview: InputsOverview
    status: List[StatusEntry]
    daily_created: List[DailySeriesEntry]


class ProductsSection(TypedDict, total=False):
    overview: ProductsOverview
    by_type: List[TypeEntry]
    daily_generated: List[DailySeriesEntry]


class ActivitySection(TypedDict, total=False):
    totals: ActivityTotals
    downloads_daily: List[DailySeriesEntry]
    generated_daily: List[DailySeriesEntry]


class FilesMetricsSnapshot(TypedDict, total=False):
    """
    Snapshot completo de métricas del módulo Files.

    Claves:
        - inputs: métricas sobre archivos insumo.
        - products: métricas sobre archivos producto.
        - activity: métricas sobre actividad de archivos producto.
    """
    inputs: InputsSection
    products: ProductsSection
    activity: ActivitySection


# Fin del archivo backend/app/modules/files/metrics/schemas/metrics_schemas.py
