
# -*- coding: utf-8 -*-
"""
backend/app/routes/__init__.py

Ensamblador principal de ruteadores de la API pública de DoxAI 2.0.

Convierte el antiguo `backend/app/routes.py` en un paquete sin romper
los imports existentes (`from app.routes import router`).

Responsabilidades:
- Incluir el router de health (/health).
- Reutilizar las capas `api` y `public` definidas en master_routes.py.

Autor: Ixchel Beristain
Fecha: 2025-11-17
"""

from fastapi import APIRouter

from .health_routes import router as health_router
from .master_routes import api, public  # reutilizamos la lógica existente

router = APIRouter()

# Health check sin prefijo adicional
router.include_router(health_router)

# Capas existentes definidas en master_routes.py
router.include_router(api)
router.include_router(public)

__all__ = ["router"]

# Fin del archivo backend\app\routes\__init__.py