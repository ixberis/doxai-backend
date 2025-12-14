
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/routes/auth_admin.py

Rutas administrativas relacionadas con autenticación, auditoría y seguridad.
Por ahora son stubs que devuelven 501 hasta que los servicios necesarios
se implementen (listado de intentos de login, sesiones, revocación masiva).

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Body

from app.modules.auth.facades.auth_facade import AuthFacade, get_auth_facade

# Usamos el mismo tag "Authentication" para agrupar en Swagger
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get(
    "/admin/login-attempts",
    summary="Listar intentos de login (no implementado aún)",
)
async def list_login_attempts(
    _facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Listado de intentos de login (para análisis/monitoreo).

    Actualmente no implementado: devolverá 501.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="No implementado aún",
    )


@router.get(
    "/admin/sessions",
    summary="Listar sesiones de usuario (no implementado aún)",
)
async def list_sessions(
    _facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Listado de sesiones de usuario (dispositivos/browsers logueados).

    Actualmente no implementado: devolverá 501.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="No implementado aún",
    )


@router.post(
    "/admin/sessions/revoke-all",
    summary="Revocar todas las sesiones (no implementado aún)",
)
async def revoke_all_sessions(
    _payload: Optional[Dict[str, Any]] = Body(default=None),
    _facade: AuthFacade = Depends(get_auth_facade),
):
    """
    Revoca todas las sesiones activas de uno o varios usuarios.

    Actualmente no implementado: devolverá 501.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="No implementado aún",
    )


# Fin del script backend/app/modules/auth/routes/auth_admin.py