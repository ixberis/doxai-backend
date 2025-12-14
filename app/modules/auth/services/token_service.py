
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/token_service.py

Utilidades de token para rutas protegidas de Auth.
Valida tipo y expiración de JWT, y expone dependencias para obtener el user_id actual.
Incluye wrapper retro-compatible `get_current_user` que retorna el objeto User.

Refactor Fase 3:
- Ajusta imports a la ubicación real de jwt_utils (app.utils.jwt_utils).
- Usa get_async_session desde app.shared.database.database.
- Se apoya en UserService, que ahora utiliza UserRepository como capa de acceso a datos.

Autor: Ixchel Beristain
Actualizado: 2025-11-19
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import TokenType
from app.modules.auth.services.user_service import UserService
from app.shared.database.database import get_async_session
from app.shared.utils.jwt_utils import decode_token, verify_token_type  # ubicación real

_bearer = HTTPBearer(auto_error=True)


async def _validate_and_get_user_id(
    token: str,
    db: AsyncSession,
    expected_type: str = "access",
    require_active_user: bool = True,
) -> str:
    """
    Valida el token (firma, expiración y tipo) y, opcionalmente, que el usuario esté activo.

    Args:
        token: JWT en texto plano.
        db: AsyncSession inyectada.
        expected_type: "access" u otro tipo según TokenType.value.
        require_active_user: Si True, verifica que el usuario asociado esté activo.

    Returns:
        user_id (sub) del token.
    """
    # verify_token_type ya decodifica y valida el tipo; devuelve payload o None
    payload = verify_token_type(token, expected_type=expected_type)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido, expirado o de tipo incorrecto",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sin 'sub' (user_id)")

    if require_active_user:
        user_service = UserService.with_session(db)
        user = await user_service.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
        if not await user_service.is_active(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo o bloqueado")

    return user_id


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
) -> str:
    """
    Dependencia para rutas que requieren:
      - Un token de acceso válido (firma + expiración).
      - Tipo de token correcto (access).
      - Usuario asociado activo.
    """
    expected_type = TokenType.access.value if hasattr(TokenType, "access") else "access"
    return await _validate_and_get_user_id(
        creds.credentials,
        db,
        expected_type=expected_type,
        require_active_user=True,
    )


async def get_optional_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
) -> Optional[str]:
    """
    Dependencia opcional: si hay token válido devuelve user_id, si no hay token o es inválido, devuelve None.
    Útil para endpoints que cambian ligeramente su comportamiento si el usuario está autenticado.
    """
    if creds is None:
        return None
    try:
        expected_type = TokenType.access.value if hasattr(TokenType, "access") else "access"
        return await _validate_and_get_user_id(
            creds.credentials,
            db,
            expected_type=expected_type,
            require_active_user=False,
        )
    except HTTPException:
        # Si el token es inválido, en esta dependencia devolvemos None (no reventamos el endpoint).
        return None


# ---- Wrapper retro-compatible ----


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Retro-compatibilidad: devuelve el objeto User (no solo el user_id).
    Permite que imports antiguos `from ...token_service import get_current_user` sigan funcionando.
    """
    user_id = await get_current_user_id(creds=creds, db=db)
    user = await UserService.with_session(db).get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    return user


__all__ = [
    "get_current_user_id",
    "get_optional_user_id",
    "get_current_user",
]

# Fin del script backend/app/modules/auth/services/token_service.py
