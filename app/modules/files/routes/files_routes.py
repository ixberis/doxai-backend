
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/routes/files_routes.py

Router principal del módulo Files (v2).

Agrupa subrutas de:
- /files/input/*     (archivos insumo)
- /files/product/*   (archivos producto)
- /files/activity/*  (actividad de archivos producto)
- /files/metrics/*   (métricas del módulo Files)

NOTA: El endpoint de reconciliación está en internal_reconcile_routes.py
y se monta bajo /_internal/files/* (requiere service token).

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from fastapi import APIRouter

# Subruteadores propios del módulo Files
from .input_files_routes import router as input_files_router
from .product_files_routes import router as product_files_router
from .activity_routes import router as activity_router

# Import selected_download_router with error handling to prevent silent failures
try:
    from .selected_download_routes import router as selected_download_router
    _selected_download_available = True
except Exception as _import_err:
    import logging as _log
    _log.getLogger(__name__).error(
        "❌ Failed to import selected_download_routes: %s",
        _import_err,
        exc_info=True,
    )
    selected_download_router = None
    _selected_download_available = False

# Métricas (router ya existente, se monta bajo /files/metrics)
try:
    from app.modules.files.metrics.routes import router as files_metrics_router  # type: ignore
except Exception:  # pragma: no cover - en dev, si aún no existe, no rompe import
    files_metrics_router = APIRouter()

router = APIRouter(prefix="/files", tags=["files"])

# Montaje de subrutas de dominio
router.include_router(input_files_router, prefix="/input", tags=["files:input"])
router.include_router(product_files_router, prefix="/product", tags=["files:product"])
router.include_router(activity_router, prefix="/activity", tags=["files:activity"])

# Montaje de descarga seleccionada (sin prefix adicional - ya tiene /{project_id}/...)
if _selected_download_available and selected_download_router is not None:
    router.include_router(selected_download_router, tags=["files:download"])
    import logging as _log
    _log.getLogger(__name__).info("✅ selected_download_router montado en /files/{project_id}/download-selected")
else:
    import logging as _log
    _log.getLogger(__name__).error("❌ selected_download_router NO montado - endpoint /download-selected no disponible")

# Montaje de métricas del módulo Files
router.include_router(files_metrics_router, prefix="/metrics", tags=["files:metrics"])

# Fin del archivo backend/app/modules/files/routes/files_routes.py