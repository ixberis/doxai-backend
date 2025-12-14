# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/__init__.py

Módulo de perfil de usuario de DoxAI.

Este módulo gestiona:
- Consulta y actualización de perfiles de usuario
- Estado de suscripciones
- Datos personales (nombre, teléfono)

Autor: DoxAI
Fecha: 2025-10-18
"""

from .schemas import (
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserProfileUpdateResponse,
)
from .services import UserProfileService
from .routes import user_profile_router

__all__ = [
    # Schemas
    "UserProfileResponse",
    "UserProfileUpdateRequest",
    "UserProfileUpdateResponse",
    
    # Services
    "UserProfileService",
    
    # Routes
    "user_profile_router",
]
