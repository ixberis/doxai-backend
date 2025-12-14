
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/routes/__init__.py

Ensamblador de routers de métricas para Files.

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""

from fastapi import APIRouter

router = APIRouter()

# Importa subrouters y los monta bajo el prefijo correcto
try:
    from .routes_snapshot_db import router as snapshot_db_router
    router.include_router(snapshot_db_router, prefix="/snapshot", tags=["files:metrics"])
except Exception:
    pass

try:
    from .routes_snapshot_memory import router as snapshot_memory_router
    router.include_router(snapshot_memory_router, prefix="/snapshot", tags=["files:metrics"])
except Exception:
    pass

try:
    from .routes_prometheus import router as prometheus_router
    router.include_router(prometheus_router, tags=["files:metrics"])
except Exception:
    pass

__all__ = ["router"]

# Fin del archivo backend/app/modules/files/metrics/routes/__init__.py
