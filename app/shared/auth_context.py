# -*- coding: utf-8 -*-
"""
backend/app/shared/auth_context.py

Helper unificado para extraer user_id y email del contexto de autenticación.

Este módulo proporciona una ÚNICA FUENTE DE VERDAD para extraer datos del
usuario autenticado, evitando duplicación de helpers en cada módulo.

═══════════════════════════════════════════════════════════════════════════════
SSOT ARCHITECTURE (2025-01-07) - CANONICAL DEFINITION
═══════════════════════════════════════════════════════════════════════════════

IDENTIDAD GLOBAL (SSOT):
    auth_user_id (UUID) - IDENTIDAD GLOBAL del usuario en DoxAI
    
    - Se genera en backend/registration durante creación de usuario
    - Se almacena en app_users.auth_user_id (NOT NULL, UNIQUE)
    - Es el ÚNICO identificador para ownership: projects.user_id, rag, billing
    - Va en JWT sub claim (SIEMPRE UUID, nunca INT)
    - NO existe "auth.users" externa - DoxAI es su propia fuente de verdad

IDENTIDAD INTERNA (ADMIN ONLY):
    user_id (int) - PK interna de app_users
    
    - Solo para administración, reportes internos, métricas
    - NUNCA usar para filtrar ownership de recursos
    - NUNCA incluir en JWT sub claim

LEGACY FALLBACK (DEPRECATION PLAN):
    user_email - Fallback temporal para usuarios sin auth_user_id
    
    - Solo usado cuando auth_user_id IS NULL (usuarios legacy pre-SSOT)
    - Loggea warning "legacy_user_email_filter_used" cuando se activa
    - CUTOFF DATE: eliminar fallback después de migración completa (TBD)
    
OWNERSHIP FLOW:
    1. Registro → genera auth_user_id = uuid4()
    2. Login → emite JWT con sub = str(auth_user_id)
    3. Request → get_current_user resuelve por auth_user_id
    4. Query → filtra por resource.user_id == auth_user_id

Autor: DoxAI
Fecha: 2025-12-27 (actualizado 2025-01-07 SSOT canónico)
"""

from __future__ import annotations

import logging
from typing import Any, Tuple, Optional
from uuid import UUID

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


def extract_auth_user_id(user: Any) -> UUID:
    """
    Extrae auth_user_id (UUID) del objeto usuario autenticado.
    
    SSOT: Este es el ID correcto para filtrar projects, rag, billing, etc.
    
    Args:
        user: Objeto usuario (AppUser) o dict del auth context
        
    Returns:
        UUID: El auth_user_id del usuario (SSOT para ownership)
        
    Raises:
        HTTPException 401: Si no hay auth_user_id válido en el contexto
    """
    # Intentar obtener auth_user_id del objeto
    auth_user_id = getattr(user, "auth_user_id", None)
    
    # Si es dict, buscar en keys
    if auth_user_id is None and isinstance(user, dict):
        auth_user_id = user.get("auth_user_id")
    
    # Validar que existe
    if auth_user_id is None:
        logger.warning("Auth context missing auth_user_id: %s", type(user).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing auth_user_id in auth context"
        )
    
    # Normalizar a UUID
    if isinstance(auth_user_id, UUID):
        return auth_user_id
    
    try:
        return UUID(str(auth_user_id))
    except (TypeError, ValueError) as e:
        logger.warning("Invalid auth_user_id format: %s (%s)", auth_user_id, e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid auth_user_id format in auth context"
        )


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


def extract_auth_user_id_and_email(user: Any) -> Tuple[UUID, str]:
    """
    Extrae auth_user_id (UUID SSOT) y email del objeto usuario autenticado.
    
    Args:
        user: Objeto usuario (AppUser) o dict del auth context
        
    Returns:
        Tuple[UUID, str]: (auth_user_id, email)
        
    Raises:
        HTTPException 401: Si falta auth_user_id o email
    """
    auth_uid = extract_auth_user_id(user)
    email = extract_user_email(user)
    
    if not email:
        logger.warning("Auth context missing email for auth_user_id=%s", auth_uid)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing email in auth context"
        )
    
    return auth_uid, email


__all__ = [
    "extract_user_id",           # INT - internal admin PK
    "extract_user_email", 
    "extract_user_id_and_email",
    "extract_auth_user_id",      # UUID - SSOT for projects/rag/billing
    "extract_auth_user_id_and_email",
]
