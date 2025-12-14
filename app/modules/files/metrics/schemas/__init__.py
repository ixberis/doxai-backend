
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/schemas/__init__.py

Tipos del snapshot de métricas de Files (TypedDicts) para Files v2.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from .metrics_schemas import (
    InputsOverview,
    ProductsOverview,
    StatusEntry,
    TypeEntry,
    DailySeriesEntry,
    ActivityTotals,
    InputsSection,
    ProductsSection,
    ActivitySection,
    FilesMetricsSnapshot,
)

__all__ = [
    "InputsOverview",
    "ProductsOverview",
    "StatusEntry",
    "TypeEntry",
    "DailySeriesEntry",
    "ActivityTotals",
    "InputsSection",
    "ProductsSection",
    "ActivitySection",
    "FilesMetricsSnapshot",
]

# Fin del archivo backend/app/modules/files/metrics/schemas/__init__.py