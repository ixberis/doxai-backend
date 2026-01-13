# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/dependencies.py

Dependencias de autenticación basadas en rol para FastAPI.

Provee:
- require_admin: Dependencia que requiere rol admin (usa get_current_user_ctx)
- require_admin_strict: Alias de require_admin

NOTE: Esta module NO contiene lógica JWT. Toda la validación de tokens
está en token_service.py. Este módulo solo expone dependencias de rol.

CANONICAL ERROR CONTRACT (inherited from get_current_user_ctx):
- Missing/invalid/expired token: 401 error="invalid_token"
- Invalid UUID sub: 401 error="invalid_user_id"
- User not found: 401 error="user_not_found"
- Inactive/locked user: 403 error="forbidden", message="User inactive or locked"
- Non-admin user: 403 error="forbidden", message="Admin access required"

Autor: DoxAI
Fecha: 2025-12-13
Actualizado: 2026-01-13 (Solo dependencias de rol - sin JWT helpers)
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# require_admin: Canonical DI using get_current_user_ctx (PUBLIC ONLY)
# ═══════════════════════════════════════════════════════════════════════════

def _create_require_admin():
    """
    Crea la dependencia require_admin con DI canónica.
    
    Usa factory pattern para evitar circular import con token_service.
    La función retornada es la ÚNICA implementación de require_admin.
    
    NO usa funciones privadas (_bearer, _validate_and_get_user_ctx, etc).
    SOLO usa get_current_user_ctx (público) que ya emite errores canónicos.
    """
    from app.modules.auth.services.token_service import get_current_user_ctx
    from app.modules.auth.schemas.auth_context_dto import AuthContextDTO
    
    async def require_admin_impl(
        ctx: AuthContextDTO = Depends(get_current_user_ctx),
    ) -> str:
        """
        Dependencia que requiere rol admin.
        
        Usa get_current_user_ctx (Core mode + cache Redis) como DI canónica.
        El AuthContextDTO ya contiene user_role, evitando queries redundantes.
        
        CANONICAL ERROR CONTRACT (inherited from get_current_user_ctx):
        - Token faltante/inválido/expirado: 401 error="invalid_token"
        - UUID inválido en sub: 401 error="invalid_user_id"
        - Usuario no encontrado: 401 error="user_not_found"
        - Usuario inactivo/bloqueado: 403 error="forbidden" message="User inactive or locked"
        - Usuario no admin: 403 error="forbidden" message="Admin access required"
        
        Returns:
            str: El auth_user_id del admin (UUID string)
        """
        # ctx ya está validado por get_current_user_ctx
        # Solo verificar rol admin
        if ctx.user_role != "admin":
            logger.info(
                "require_admin_forbidden auth_user_id=%s role=%s",
                str(ctx.auth_user_id)[:8] + "...",
                ctx.user_role,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": "Admin access required",
                },
            )
        
        return str(ctx.auth_user_id)
    
    return require_admin_impl


# Única implementación exportada - usa SOLO APIs públicas
require_admin = _create_require_admin()

# Alias para compatibilidad - ambos son idénticos ahora
# (get_current_user_ctx ya emite errores canónicos con dict)
require_admin_strict = require_admin


__all__ = [
    "require_admin",
    "require_admin_strict",  # Alias - same as require_admin
]
