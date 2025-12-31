# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/routes/__init__.py

Rutas del módulo de perfil de usuario.

Autor: DoxAI
Fecha: 2025-10-18
"""

from fastapi import APIRouter

from .profile_routes import router as user_profile_router
from .tax_profile_routes import router as tax_profile_router

# Combined router that includes both profile and tax profile routes
# profile_routes has no prefix, tax_profile_routes has no prefix
# When mounted under /api/profile, this gives:
# - /api/profile, /api/profile/profile, /api/profile/subscription (profile_routes)
# - /api/profile/tax-profile, /api/profile/tax-profile/cedula (tax_profile_routes)
combined_router = APIRouter(prefix="/profile", tags=["User Profile"])
combined_router.include_router(user_profile_router)
combined_router.include_router(tax_profile_router)

__all__ = ["user_profile_router", "tax_profile_router", "combined_router"]
