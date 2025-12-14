
# -*- coding: utf-8 -*-
"""
backend/app/routes/health_routes.py

Endpoint básico de health check para el backend de DoxAI 2.0.

Autor: Ixchel Beristain
Fecha: 2025-11-17
"""

from datetime import datetime

from fastapi import APIRouter

from app.core.settings import get_settings
from app.core.db import check_database_health

router = APIRouter()


@router.get(
    "/health",
    summary="Health check del backend",
    description=(
        "Devuelve el estado básico del backend DoxAI 2.0, incluyendo "
        "verificación simple de conectividad a la base de datos."
    ),
)
async def health_check() -> dict:
    """
    Health check básico del backend.

    Returns:
        dict: información mínima de estado de la aplicación.
    """
    settings = get_settings()

    db_ok = await check_database_health(timeout_s=2.0)

    return {
        "status": "ok" if db_ok else "degraded",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": settings.python_env,
        "database": {
            "reachable": db_ok,
        },
        "service": {
            "name": "doxai-backend",
            "version": "2.0-base",
        },
    }

# Fin del archivo backend\app\routes\health_routes.py