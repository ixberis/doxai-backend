# -*- coding: utf-8 -*-
"""
backend/app/shared/internal_auth.py

Autenticación de servicio interno para endpoints protegidos (cron jobs, admin, etc.).

Módulo separado de auth.dependencies.py (JWT user auth) para mantener
la separación de responsabilidades.

Uso:
    from app.shared.internal_auth import InternalServiceAuth, require_internal_service_token

Autor: DoxAI
Fecha: 2025-12-14
"""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

logger = logging.getLogger(__name__)


async def require_internal_service_token(
    authorization: Annotated[str | None, Header()] = None,
    x_service_token: Annotated[str | None, Header(alias="X-Service-Token")] = None,
) -> bool:
    """
    Valida que el request contenga un token de servicio interno válido.
    
    Soporta DOS formatos de autenticación:
    1. Authorization: Bearer <token>
    2. X-Service-Token: <token>
    
    Compara contra settings.internal_service_token (APP_SERVICE_TOKEN).
    
    Args:
        authorization: Header Authorization del request.
        x_service_token: Header X-Service-Token del request.
        
    Returns:
        True si la validación es exitosa.
        
    Raises:
        HTTPException 401: Si no hay header de autenticación.
        HTTPException 403: Si el token es inválido.
        HTTPException 500: Si el token no está configurado en el backend.
    """
    from app.shared.config.config_loader import get_settings
    
    settings = get_settings()
    
    # Verificar que el token de servicio está configurado
    if not settings.internal_service_token:
        logger.error(
            "internal_service_token_not_configured: "
            "APP_SERVICE_TOKEN must be set for internal endpoints"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal service token not configured",
        )
    
    # Extraer token desde X-Service-Token o Authorization: Bearer
    provided_token: str | None = None
    
    if x_service_token:
        # X-Service-Token tiene prioridad (más simple)
        provided_token = x_service_token
    elif authorization:
        # Parsear Bearer token
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_token = parts[1]
        else:
            logger.warning("internal_auth_invalid_format")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization format. Use: Bearer <token> or X-Service-Token header",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # Verificar presencia de algún token
    if not provided_token:
        logger.warning("internal_auth_missing_header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required. Use: Authorization: Bearer <token> or X-Service-Token header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Soportar tanto SecretStr como str para compatibilidad con tests
    token_value = settings.internal_service_token
    expected_token = token_value.get_secret_value() if hasattr(token_value, 'get_secret_value') else str(token_value)
    
    # Comparación timing-safe para prevenir timing attacks
    if not secrets.compare_digest(provided_token, expected_token):
        logger.warning("internal_auth_invalid_token")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid service token",
        )
    
    logger.debug("internal_auth_success")
    return True


# Type alias para uso en endpoints con Depends()
InternalServiceAuth = Annotated[bool, Depends(require_internal_service_token)]


__all__ = [
    "require_internal_service_token",
    "InternalServiceAuth",
]
