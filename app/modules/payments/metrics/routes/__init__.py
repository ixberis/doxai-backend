
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/routes/__init__.py

Routers de métricas (divididos por responsabilidad) y router combinado.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from fastapi import APIRouter

# Importaciones robustas con try-except para cada router
try:
    from .routes_prometheus import router_prometheus
except Exception as e:
    import logging
    logging.warning(f"Failed to import router_prometheus: {e}")
    router_prometheus = APIRouter()  # Router vacío como fallback

try:
    from .routes_snapshot_memory import router_snapshot_memory
except Exception as e:
    import logging
    logging.warning(f"Failed to import router_snapshot_memory: {e}")
    router_snapshot_memory = APIRouter()  # Router vacío como fallback

try:
    from .routes_snapshot_db import router_snapshot_db
except Exception as e:
    import logging
    logging.warning(f"Failed to import router_snapshot_db: {e}")
    router_snapshot_db = APIRouter()  # Router vacío como fallback

# Router combinado (opcional): te permite incluir TODO con una sola importación
# IMPORTANTE: Los routers ya tienen su prefix="/metrics" definido
router = APIRouter()
router.include_router(router_prometheus, prefix="")
router.include_router(router_snapshot_memory, prefix="")
router.include_router(router_snapshot_db, prefix="")

__all__ = [
    "router_prometheus",
    "router_snapshot_memory",
    "router_snapshot_db",
    "router",
]

# Fin del archivo backend\app\modules\payments\metrics\routes\__init__.py