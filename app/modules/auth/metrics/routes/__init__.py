
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/__init__.py

Ensamblador de ruteadores de métricas del módulo Auth.

Expone una variable `router` para que otros módulos puedan hacer:

    from app.modules.auth.metrics.routes import router as metrics_auth_router

y montar todas las rutas de métricas de autenticación de una sola vez.

Autor: Ixchel Beristain
Fecha: 20/11/2025
Actualizado: 2025-12-26 - Agregadas rutas de emails
Actualizado: 2026-01-03 - Agregadas rutas operativas
"""

from __future__ import annotations

from fastapi import APIRouter

from .metrics_routes import router as metrics_routes_router
from .email_routes import router as email_routes_router
from .operational_routes import router as operational_routes_router
from .functional_routes import router as functional_routes_router
from .alert_routes import router as alert_routes_router

# Router maestro de métricas de Auth
router = APIRouter(tags=["metrics-auth"])

# Incluimos el router real definido en metrics_routes.py
router.include_router(metrics_routes_router)

# Incluimos rutas de métricas de emails
router.include_router(email_routes_router)

# Incluimos rutas operativas
router.include_router(operational_routes_router)

# Incluimos rutas funcionales (activation, password-reset, users)
router.include_router(functional_routes_router)

# Incluimos rutas de gestión de alertas (ACK/SNOOZE)
router.include_router(alert_routes_router)

__all__ = ["router"]

# Fin del archivo backend/app/modules/auth/metrics/routes/__init__.py