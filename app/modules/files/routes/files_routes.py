
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/routes/files_routes.py

Router principal del módulo Files (v2).

Agrupa subrutas de:
- /files/input/*     (archivos insumo)
- /files/product/*   (archivos producto)
- /files/activity/*  (actividad de archivos producto)
- /files/metrics/*   (métricas del módulo Files)

Este router debe ser incluido desde el ensamblador principal de la app
para exponer todo bajo el prefijo /files.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations

from fastapi import APIRouter

# Subruteadores propios del módulo Files
from .input_files_routes import router as input_files_router
from .product_files_routes import router as product_files_router
from .activity_routes import router as activity_router

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

# Montaje de métricas del módulo Files
router.include_router(files_metrics_router, prefix="/metrics", tags=["files:metrics"])

# Fin del archivo backend/app/modules/files/routes/files_routes.py