# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/__init__.py

Punto de entrada del paquete services de Auth.
Expone dependencias y utilidades usadas por rutas y otros módulos.
Incluye un wrapper retro-compatible `get_current_user` que retorna el objeto User,
usando la nueva función `get_current_user_id` de token_service.

Autor: Ixchel Beristain
Actualizado: 18/10/2025
Updated: 2026-01-09 - SSOT: JWT sub = auth_user_id (UUID). Resolver usuario por UUID, con fallback legacy a user_id INT.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.services.token_service import (
    get_current_user_id,
    get_optional_user_id,
)

logger = logging.getLogger(__name__)

# Export explícito de lo que otros módulos suelen importar
__all__ = [
    "get_current_user",          # retro-compatibilidad
    "get_current_user_id",
    "get_optional_user_id",
]

_bearer = HTTPBearer(auto_error=True)


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Retro-compatibilidad: devuelve el objeto User (no solo el user_id).

    BD 2.0 SSOT:
      - JWT sub = auth_user_id (UUID)
    Legacy transitorio:
      - JWT sub podría ser user_id (INT)

    Internamente usa get_current_user_id(...) para validar el token y extraer el sub.
    Luego resuelve el usuario por auth_user_id (UUID) y, si no aplica, hace fallback a user_id (INT).
    """
    # Importación local para evitar ciclos de import
    from app.modules.auth.services.user_service import UserService

    # `get_current_user_id` retorna el `sub` del token (string)
    sub: str = await get_current_user_id(creds=creds, db=db)

    # Canónico: usar sesión prestada explícitamente
    user_service = UserService.with_session(db)

    # 1) SSOT: intentar resolver como UUID (auth_user_id)
    try:
        auth_user_id = UUID(sub)
        user = await user_service.get_by_auth_user_id(auth_user_id)
        if user:
            return user
    except (ValueError, TypeError):
        # No es UUID, intentar legacy abajo
        pass

    # 2) Legacy fallback: resolver como INT (user_id)
    try:
        user_id_int = int(sub)
    except (ValueError, TypeError):
        logger.warning(
            "invalid_token_sub_not_uuid_or_int sub_prefix=%s",
            (sub[:8] + "...") if isinstance(sub, str) else "non-str",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )

    user = await user_service.get_by_id(user_id_int)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )

    # Aviso: token legacy usando sub INT (transitorio)
    logger.warning("legacy_token_sub_int_used user_id=%s", user_id_int)
    return user


# Fin del archivo

