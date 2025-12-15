
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/routes/__init__.py

Ensamblador de ruteadores de métricas del módulo Auth.

Expone una variable `router` para que otros módulos puedan hacer:

    from app.modules.auth.metrics.routes import router as metrics_auth_router

y montar todas las rutas de métricas de autenticación de una sola vez.

Autor: Ixchel Beristain
Fecha: 20/11/2025
"""

from __future__ import annotations

from fastapi import APIRouter

from .metrics_routes import router as metrics_routes_router

# Router maestro de métricas de Auth
router = APIRouter(tags=["metrics-auth"])

# Incluimos el router real definido en metrics_routes.py
router.include_router(metrics_routes_router)

__all__ = ["router"]

# Fin del archivo backend/app/modules/auth/metrics/routes/__init__.py