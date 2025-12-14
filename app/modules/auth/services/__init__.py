
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/__init__.py

Punto de entrada del paquete services de Auth.
Expone dependencias y utilidades usadas por rutas y otros módulos.
Incluye un wrapper retro-compatible `get_current_user` que retorna el objeto User,
usando la nueva función `get_current_user_id` de token_service.

Autor: Ixchel Beristain
Actualizado: 18/10/2025
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.modules.auth.services.token_service import (
    get_current_user_id,
    get_optional_user_id,
)

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
    Internamente usa get_current_user_id(...) para validar el token.
    """
    # Importación local para evitar ciclos de import
    from app.modules.auth.services.user_service import UserService

    user_id: str = await get_current_user_id(creds=creds, db=db)
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")
    return user
# Fin del archivo
