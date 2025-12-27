# -*- coding: utf-8 -*-
"""
backend/app/shared/auth_context.py

Helper unificado para extraer user_id y email del contexto de autenticación.

Este módulo proporciona una ÚNICA FUENTE DE VERDAD para extraer datos del
usuario autenticado, evitando duplicación de helpers en cada módulo.

Tipo de user_id: int (coincide con app_users.user_id en PostgreSQL)

Autor: DoxAI
Fecha: 2025-12-27
"""

from __future__ import annotations

import logging
from typing import Any, Tuple, Optional

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def extract_user_id(user: Any) -> int:
    """
    Extrae user_id (int) del objeto usuario autenticado.
    
    IMPORTANTE: NO usa fallback a 'id' - solo 'user_id' es válido.
    El modelo AppUser usa user_id (int) como PK.
    
    Args:
        user: Objeto usuario (AppUser) o dict del auth context
        
    Returns:
        int: El user_id del usuario
        
    Raises:
        HTTPException 401: Si no hay user_id válido en el contexto
    """
    # Intentar obtener user_id del objeto
    user_id = getattr(user, "user_id", None)
    
    # Si es dict, buscar en keys
    if user_id is None and isinstance(user, dict):
        user_id = user.get("user_id")
    
    # Validar que existe
    if user_id is None:
        logger.warning("Auth context missing user_id: %s", type(user).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user_id in auth context"
        )
    
    # Normalizar a int (AppUser.user_id es int)
    try:
        return int(user_id) if not isinstance(user_id, int) else user_id
    except (TypeError, ValueError) as e:
        logger.warning("Invalid user_id format: %s (%s)", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user_id format in auth context"
        )


def extract_user_email(user: Any) -> Optional[str]:
    """
    Extrae email del objeto usuario autenticado.
    
    Tolera tanto 'user_email' como 'email' como nombres de atributo.
    
    Args:
        user: Objeto usuario (AppUser) o dict del auth context
        
    Returns:
        str | None: El email del usuario, o None si no está disponible
    """
    # Intentar obtener email del objeto (prefiere user_email)
    email = getattr(user, "user_email", None) or getattr(user, "email", None)
    
    # Si es dict, buscar en keys
    if email is None and isinstance(user, dict):
        email = user.get("user_email") or user.get("email")
    
    return email


def extract_user_id_and_email(user: Any) -> Tuple[int, str]:
    """
    Extrae user_id (int) y email del objeto usuario autenticado.
    
    Combina extract_user_id y extract_user_email, pero requiere que
    ambos estén presentes.
    
    Args:
        user: Objeto usuario (AppUser) o dict del auth context
        
    Returns:
        Tuple[int, str]: (user_id, email)
        
    Raises:
        HTTPException 401: Si falta user_id o email
    """
    uid = extract_user_id(user)
    email = extract_user_email(user)
    
    if not email:
        logger.warning("Auth context missing email for user_id=%s", uid)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing email in auth context"
        )
    
    return uid, email


__all__ = [
    "extract_user_id",
    "extract_user_email", 
    "extract_user_id_and_email",
]
