
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/collectors/metrics_collector.py

Colector simple para publicar contadores en memoria (placeholder).

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations

from typing import Dict, Any
from ..aggregators.metrics_storage import update_memory


class MetricsCollector:
    def publish(self, payload: Dict[str, Any]) -> None:
        update_memory(payload)


# Fin del archivo backend/app/modules/files/metrics/collectors/metrics_collector.py
