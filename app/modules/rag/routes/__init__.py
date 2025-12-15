
# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/routes/__init__.py

Ensamblador principal de rutas del módulo RAG (Fase 1 – Indexación).

Incluye:
- /rag/indexing/...       → gestión y reindexación de jobs
- /rag/status/...         → estado de documentos y proyectos
- /rag/ocr/...            → callbacks y administración de OCR
- /rag/diagnostics/...    → vistas de diagnóstico
- /rag/metrics/...        → métricas Prometheus y snapshots

Este router debe ser incluido en `app.main` (o en el ensamblador general
de módulos) con un prefijo `/rag` para mantener contratos estables.

Autor: Ixchel Beristáin Mendoza
Fecha: 17/11/2025
"""

from fastapi import APIRouter

from app.modules.rag.routes.indexing.routes_indexing_jobs import (
    router as indexing_jobs_router,
)
from app.modules.rag.routes.indexing.routes_indexing_reindex import (
    router as indexing_reindex_router,
)
from app.modules.rag.routes.status.routes_documents_status import (
    router as documents_status_router,
)
from app.modules.rag.routes.status.routes_projects_status import (
    router as projects_status_router,
)
from app.modules.rag.routes.ocr.routes_ocr_callbacks import (
    router as ocr_callbacks_router,
)
from app.modules.rag.routes.ocr.routes_ocr_admin import (
    router as ocr_admin_router,
)
from app.modules.rag.routes.diagnostics.routes_diagnostics import (
    router as diagnostics_router,
)
from app.modules.rag.metrics.routes import router as rag_metrics_router

router = APIRouter(tags=["rag"])

# Indexación
router.include_router(indexing_jobs_router)
router.include_router(indexing_reindex_router)

# Estado RAG
router.include_router(documents_status_router)
router.include_router(projects_status_router)

# OCR
router.include_router(ocr_callbacks_router)
router.include_router(ocr_admin_router)

# Diagnóstico
router.include_router(diagnostics_router)

# Métricas
router.include_router(rag_metrics_router)


def get_rag_routers():
    """
    Devuelve el router principal del módulo RAG.
    
    Patrón v2: permite montar el módulo RAG desde app.main
    de forma consistente con otros módulos (auth, payments, projects, files).
    """
    return router


# Fin del archivo backend/app/modules/rag/routes/__init__.py
