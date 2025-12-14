# -*- coding: utf-8 -*-
"""
backend/app/shared/routes/legacy_compatibility_routes.py

Wrappers explícitos para rutas legacy que necesitan lógica especial
o no pueden ser manejadas solo por el middleware.

Estos wrappers se pueden remover después del período de sunset (90 días).

Autor: DoxAI
Fecha: 2025-10-18
"""

from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import logging

logger = logging.getLogger(__name__)

# Fecha de sunset
SUNSET_DATE = "Wed, 16 Jan 2026 00:00:00 GMT"

# Router para compatibilidad
compat_router = APIRouter(
    tags=["Legacy Compatibility"],
    include_in_schema=False  # No mostrar en OpenAPI docs
)


def create_legacy_redirect(new_path: str, legacy_path: str):
    """
    Factory para crear funciones de redirect reutilizables.
    """
    async def redirect_handler(request: Request):
        """Handler de redirect con deprecation headers."""
        logger.warning(
            f"🔄 [LEGACY] Request a ruta deprecada: {legacy_path} → {new_path} "
            f"(User-Agent: {request.headers.get('user-agent', 'unknown')})"
        )
        
        # Preservar query params
        query_string = request.url.query
        full_url = f"{new_path}?{query_string}" if query_string else new_path
        
        response = RedirectResponse(url=full_url, status_code=307)
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = SUNSET_DATE
        response.headers["X-Legacy-Path"] = legacy_path
        response.headers["X-New-Path"] = new_path
        response.headers["Warning"] = (
            f'299 - "Ruta deprecada. Migre a {new_path} antes del 2026-01-16"'
        )
        
        return response
    
    return redirect_handler


# ============================================================================
# AUTH LEGACY REDIRECTS
# ============================================================================

@compat_router.post("/auth/register", include_in_schema=False)
async def legacy_auth_register(request: Request):
    """Legacy: /auth/register → /api/auth/register"""
    return await create_legacy_redirect("/api/auth/register", "/auth/register")(request)


@compat_router.post("/auth/activate", include_in_schema=False)
async def legacy_auth_activate(request: Request):
    """Legacy: /auth/activate → /api/auth/activate"""
    return await create_legacy_redirect("/api/auth/activate", "/auth/activate")(request)


@compat_router.post("/auth/resend-activation", include_in_schema=False)
async def legacy_auth_resend(request: Request):
    """Legacy: /auth/resend-activation → /api/auth/resend-activation"""
    return await create_legacy_redirect("/api/auth/resend-activation", "/auth/resend-activation")(request)


@compat_router.post("/auth/login", include_in_schema=False)
async def legacy_auth_login(request: Request):
    """Legacy: /auth/login → /api/auth/login"""
    return await create_legacy_redirect("/api/auth/login", "/auth/login")(request)


@compat_router.post("/auth/refresh", include_in_schema=False)
async def legacy_auth_refresh(request: Request):
    """Legacy: /auth/refresh → /api/auth/refresh"""
    return await create_legacy_redirect("/api/auth/refresh", "/auth/refresh")(request)


# ============================================================================
# PROFILE LEGACY REDIRECTS
# ============================================================================

@compat_router.get("/profile", include_in_schema=False)
async def legacy_profile_get(request: Request):
    """Legacy: /profile → /api/profile"""
    return await create_legacy_redirect("/api/profile", "/profile")(request)


@compat_router.put("/profile", include_in_schema=False)
async def legacy_profile_put(request: Request):
    """Legacy: /profile → /api/profile"""
    return await create_legacy_redirect("/api/profile", "/profile")(request)


@compat_router.get("/profile/subscription", include_in_schema=False)
async def legacy_profile_subscription(request: Request):
    """Legacy: /profile/subscription → /api/profile/subscription"""
    return await create_legacy_redirect("/api/profile/subscription", "/profile/subscription")(request)


# ============================================================================
# RAG LEGACY REDIRECTS (doble prefijo)
# ============================================================================

@compat_router.post("/rag/api/rag/indexing/start", include_in_schema=False)
async def legacy_rag_indexing_start(request: Request):
    """Legacy: /rag/api/rag/indexing/start → /api/rag/indexing/start"""
    return await create_legacy_redirect("/api/rag/indexing/start", "/rag/api/rag/indexing/start")(request)


# ============================================================================
# PAYMENTS LEGACY REDIRECTS
# ============================================================================

@compat_router.post("/payments/abandon", include_in_schema=False)
async def legacy_payments_abandon(request: Request):
    """Legacy: /payments/abandon → /api/payments/abandon"""
    return await create_legacy_redirect("/api/payments/abandon", "/payments/abandon")(request)


# TODO: Agregar más redirects según sea necesario
# Los redirects genéricos de prefijos son manejados por el middleware

# Export router
router = compat_router
