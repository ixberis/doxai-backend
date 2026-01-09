
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/token_service.py

Utilidades de token para rutas protegidas de Auth.
Valida tipo y expiración de JWT, y expone dependencias para obtener el usuario actual.
Incluye wrapper retro-compatible `get_current_user` que retorna el objeto User.

SSOT Architecture (2025-01-07):
- JWT sub contiene auth_user_id (UUID), NO user_id (INT)
- _validate_and_get_user resuelve UUID primero, con fallback a INT para tokens legacy
- get_current_user_id retorna auth_user_id (UUID string)
- get_current_user retorna el objeto AppUser completo

Autor: Ixchel Beristain
Actualizado: 2025-01-07 (SSOT auth_user_id)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import TokenType
from app.modules.auth.services.user_service import UserService
from app.shared.database.database import get_async_session
from app.shared.utils.jwt_utils import verify_token_type

_bearer = HTTPBearer(auto_error=True)
logger = logging.getLogger(__name__)


async def _validate_and_get_user(
    token: str,
    db: AsyncSession,
    expected_type: str = "access",
    require_active_user: bool = True,
):
    """
    Valida el token (firma, expiración y tipo) y resuelve el usuario.
    
    SSOT: sub puede ser auth_user_id (UUID nuevo) o user_id (INT legacy).
    Prefiere auth_user_id, con fallback a user_id durante transición.

    Args:
        token: JWT en texto plano.
        db: AsyncSession inyectada.
        expected_type: "access" u otro tipo según TokenType.value.
        require_active_user: Si True, verifica que el usuario asociado esté activo.

    Returns:
        AppUser object.
    """
    from uuid import UUID as PyUUID
    
    # verify_token_type ya decodifica y valida el tipo; devuelve payload o None
    payload = verify_token_type(token, expected_type=expected_type)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido, expirado o de tipo incorrecto",
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sin 'sub' (user_id)")

    user_service = UserService.with_session(db)
    user = None
    
    # ═══════════════════════════════════════════════════════════════════════
    # SSOT: Resolver usuario por auth_user_id (UUID) - ruta principal
    # ═══════════════════════════════════════════════════════════════════════
    try:
        auth_user_id = PyUUID(sub)
        user = await user_service.get_by_auth_user_id(auth_user_id)
    except ValueError:
        pass  # No es UUID, intentar como INT (legacy)
    
    # Fallback: sub es user_id INT (legacy transitorio)
    if not user:
        try:
            user_id_int = int(sub)
            user = await user_service.get_by_id(user_id_int)
            if user:
                logger.warning(
                    "legacy_token_sub_int_used user_id=%s - migrando a auth_user_id UUID",
                    user_id_int,
                )
                # Fix legacy: generar auth_user_id si no existe
                if user.auth_user_id is None:
                    from uuid import uuid4
                    user.auth_user_id = uuid4()
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    logger.warning(
                        "legacy_user_missing_auth_user_id_fixed user_id=%s new_auth_user_id=%s",
                        user_id_int,
                        str(user.auth_user_id)[:8] + "...",
                    )
        except ValueError:
            pass

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    
    if require_active_user:
        if not await user_service.is_active(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo o bloqueado")

    return user


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
) -> str:
    """
    Dependencia para rutas que requieren un token válido.
    Retorna auth_user_id (UUID como string) del usuario.
    """
    expected_type = TokenType.access.value if hasattr(TokenType, "access") else "access"
    user = await _validate_and_get_user(
        creds.credentials,
        db,
        expected_type=expected_type,
        require_active_user=True,
    )
    # SSOT: Retornar auth_user_id (UUID)
    return str(user.auth_user_id)


async def get_optional_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
) -> Optional[str]:
    """
    Dependencia opcional: si hay token válido devuelve auth_user_id (UUID), 
    si no hay token o es inválido, devuelve None.
    """
    if creds is None:
        return None
    try:
        expected_type = TokenType.access.value if hasattr(TokenType, "access") else "access"
        user = await _validate_and_get_user(
            creds.credentials,
            db,
            expected_type=expected_type,
            require_active_user=False,
        )
        return str(user.auth_user_id)
    except HTTPException:
        return None


# ---- Wrapper retro-compatible ----


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retro-compatibilidad: devuelve el objeto User completo.
    Permite que imports antiguos `from ...token_service import get_current_user` sigan funcionando.
    """
    expected_type = TokenType.access.value if hasattr(TokenType, "access") else "access"
    return await _validate_and_get_user(
        creds.credentials,
        db,
        expected_type=expected_type,
        require_active_user=True,
    )


__all__ = [
    "get_current_user_id",
    "get_optional_user_id",
    "get_current_user",
]

# Fin del script backend/app/modules/auth/services/token_service.py
