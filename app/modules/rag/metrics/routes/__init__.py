# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/metrics/routes/__init__.py

Ensamblador de ruteadores de métricas del módulo RAG.

Incluye:
- /rag/metrics/prometheus     → Exportador Prometheus
- /rag/metrics/snapshot/db    → Snapshot de KPIs desde base de datos
- /rag/metrics/snapshot/memory→ Snapshot de estado en memoria (workers, jobs)

Este router se debe incluir desde el ensamblador principal del módulo RAG
(`backend/app/modules/rag/routes/__init__.py`) para que los paths queden bajo
el prefijo /rag.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from fastapi import APIRouter

from app.modules.rag.metrics.routes.routes_prometheus import (
    router as prometheus_router,
)
from app.modules.rag.metrics.routes.routes_snapshot_db import (
    router as snapshot_db_router,
)
from app.modules.rag.metrics.routes.routes_snapshot_memory import (
    router as snapshot_memory_router,
)

router = APIRouter()

# Exportador Prometheus
router.include_router(prometheus_router)

# Snapshots de KPIs desde base de datos
router.include_router(snapshot_db_router)

# Snapshots de estado en memoria
router.include_router(snapshot_memory_router)


# Fin del archivo backend/app/modules/rag/metrics/routes/__init__.py
