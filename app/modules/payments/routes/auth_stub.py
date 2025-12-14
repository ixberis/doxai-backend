# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/auth_stub.py

Stub de autenticación FAIL-CLOSED para checkout.

REGLAS DE SEGURIDAD:
- En producción (ENVIRONMENT=production o PYTHON_ENV=production):
  → Siempre 401. No acepta tokens sin validación JWT real.
  → ALLOW_DEMO_USER se ignora completamente.

- En desarrollo/test:
  → ALLOW_DEMO_USER=true → permite "demo-user"
  → Bearer token presente → deriva user_id para tests

Autor: DoxAI
Fecha: 2025-12-13
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException, Header, status


def _is_production() -> bool:
    """Detecta si estamos en entorno de producción."""
    env = os.getenv("ENVIRONMENT", "").lower()
    python_env = os.getenv("PYTHON_ENV", "").lower()
    return env == "production" or python_env == "production"


def _is_demo_allowed() -> bool:
    """
    Verifica si demo-user está permitido.
    
    Solo funciona si:
    - ALLOW_DEMO_USER=true
    - Y NO estamos en producción
    """
    if _is_production():
        return False  # Nunca en producción
    return os.getenv("ALLOW_DEMO_USER", "").lower() == "true"


async def get_current_user_id(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    Dependencia de autenticación para checkout (FAIL-CLOSED).
    
    PRODUCCIÓN:
    - Siempre retorna 401. Requiere integración real de JWT.
    - ALLOW_DEMO_USER se ignora.
    
    DESARROLLO/TEST:
    - Si ALLOW_DEMO_USER=true: retorna "demo-user"
    - Si hay Bearer token: deriva user_id del token (para tests)
    - Sin auth: 401
    
    TODO: Integrar con sistema real de auth (JWT validation) para producción.
    """
    # === PRODUCCIÓN: FAIL-CLOSED ===
    if _is_production():
        # En producción, este stub NO debe usarse.
        # Debe reemplazarse por validación JWT real.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "auth_not_configured",
                "message": "Authentication not configured for production. "
                           "Please integrate real JWT validation.",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # === DESARROLLO/TEST ===
    
    # Modo demo (solo en dev/test)
    if _is_demo_allowed():
        return "demo-user"
    
    # Sin header de auth
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "authentication_required",
                "message": "Authorization header is required",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Validar formato Bearer token
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token_format",
                "message": "Authorization header must be 'Bearer <token>'",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization[7:]  # Remove "Bearer "
    
    # Validar token mínimo (para tests)
    if not token or len(token) < 10:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "Invalid or expired token",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # En dev/test: derivar user_id del token (para tests funcionales)
    return f"user_{token[:8]}"


__all__ = ["get_current_user_id"]
