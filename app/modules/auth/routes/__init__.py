
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/routes/__init__.py

Ensambla los routers públicos / tokens / admin / métricas del módulo Auth.
Se importa desde master_routes.py para montar sobre / y /api.

Autor: Ixchel Beristain
Fecha: 20/11/2025
"""

from fastapi import APIRouter

from .auth_public import router as auth_public_router
from .auth_tokens import router as auth_tokens_router
from .auth_admin import router as auth_admin_router

# Métricas del módulo Auth
from ..metrics.routes import router as metrics_auth_router   # noqa


def get_auth_routers() -> list[APIRouter]:
    """Devuelve todos los routers listos para montar."""
    return [
        auth_public_router,
        auth_tokens_router,
        auth_admin_router,
        metrics_auth_router,
    ]

# Fin del archivo backend/app/modules/auth/routes/__init__.py
