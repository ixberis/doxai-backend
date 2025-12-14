
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/routes/routes_snapshot_memory.py

Snapshot de métricas en memoria (si se instrumentan collectors opcionales).

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations

from fastapi import APIRouter
from typing import Any, Dict

from ..aggregators.metrics_storage import snapshot_memory

router = APIRouter(tags=["files:metrics"])


@router.get("/memory")
def files_metrics_snapshot_memory() -> Dict[str, Any]:
    return snapshot_memory()


# Fin del archivo backend/app/modules/files/metrics/routes/routes_snapshot_memory.py
