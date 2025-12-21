# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/dependencies.py

Dependencias de autenticación JWT para FastAPI.

Provee:
- validate_jwt_token: Core logic para validar token (única fuente de verdad)
- get_current_user_id: Dependencia FastAPI con oauth2_scheme

NOTA: La autenticación de servicio interno (InternalServiceAuth) está en
app.shared.internal_auth para mantener separación de responsabilidades.

Autor: DoxAI
Fecha: 2025-12-13
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status

from .security import oauth2_scheme, decode_access_token, TokenDecodeError

logger = logging.getLogger(__name__)


def validate_jwt_token(token: str) -> str:
    """
    Valida un JWT y extrae el user_id.
    
    Esta es la ÚNICA FUENTE DE VERDAD para validación JWT.
    Usada por get_current_user_id y otros módulos que necesitan validar tokens.
    
    Args:
        token: JWT token string (sin prefijo "Bearer ")
    
    Raises:
        HTTPException 401: Si el token es inválido o expirado.
    
    Returns:
        str: El user_id extraído del token JWT (claim 'sub').
    """
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "invalid_token",
                    "message": "Token does not contain user identifier",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return str(user_id)
        
    except TokenDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": str(e),
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_user_id(
    token: str = Depends(oauth2_scheme),
) -> str:
    """
    Dependencia de autenticación para endpoints protegidos.
    
    Extrae y valida el JWT del header Authorization: Bearer <token>.
    Usa validate_jwt_token como única fuente de verdad.
    
    Returns:
        str: El user_id extraído del token JWT.
    """
    return validate_jwt_token(token)


async def require_admin(
    token: str = Depends(oauth2_scheme),
) -> str:
    """
    Dependencia que requiere rol admin.
    
    Valida JWT y verifica que el usuario tenga rol 'admin' en app_users.
    Para endpoints administrativos internos.
    
    Raises:
        HTTPException 401: Token inválido
        HTTPException 403: Usuario no es admin
    
    Returns:
        str: El user_id del admin
    """
    user_id = validate_jwt_token(token)
    
    # Import here to avoid circular dependency
    from app.shared.database.database import SessionLocal
    from sqlalchemy import text
    
    async with SessionLocal() as db:
        query = text("""
            SELECT user_role::text 
            FROM public.app_users 
            WHERE user_id = :uid
        """)
        result = await db.execute(query, {"uid": user_id})
        row = result.first()
        
        if not row or row[0] != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": "Admin access required",
                },
            )
    
    return user_id


__all__ = [
    "get_current_user_id",
    "validate_jwt_token",
    "require_admin",
]
