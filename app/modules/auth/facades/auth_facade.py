
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/facades/auth_facade.py

Fachada del módulo Auth.

Proporciona una interfaz estable para las rutas:
    - register_user
    - activate_account
    - resend_activation_email
    - forgot_password
    - reset_password
    - login
    - refresh_token
    - logout (stub)
    - me (stub)

Internamente delega en AuthService, que a su vez utiliza los flow services
(RegistrationFlowService, ActivationFlowService, LoginFlowService,
PasswordResetFlowService) y la capa de servicios/repositorios.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

from typing import Any, Mapping, Dict

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.services.auth_service import AuthService
from app.shared.database.database import get_async_session


class AuthFacade:
    """
    Fachada de alto nivel para operaciones de autenticación.

    Nota:
        Esta clase existe principalmente para ofrecer una interfaz estable a las rutas
        y para facilitar pruebas/mocks en otros módulos. La lógica de negocio se
        encuentra en AuthService y en los flow services.
    """

    def __init__(self, auth_service: AuthService) -> None:
        self._service = auth_service

    # ---------------------- Registro ---------------------- #

    async def register_user(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """Flujo de registro de usuario."""
        return await self._service.register_user(data)

    # Alias por si alguna ruta/cliente usa el nombre corto
    async def register(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        return await self._service.register_user(data)

    # ---------------------- Activación ---------------------- #

    async def activate_account(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """Flujo de activación de cuenta."""
        return await self._service.activate_account(data)

    async def resend_activation_email(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """Reenvío de correo de activación."""
        return await self._service.resend_activation_email(data)

    # ---------------------- Password reset ---------------------- #

    async def forgot_password(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Inicio de restablecimiento de contraseña.
        Se mapea al método start_password_reset de AuthService.
        """
        return await self._service.start_password_reset(data)

    async def reset_password(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """
        Confirmación de restablecimiento de contraseña.
        Se mapea al método confirm_password_reset de AuthService.
        """
        return await self._service.confirm_password_reset(data)

    # ---------------------- Login / Tokens ---------------------- #

    async def login(
        self, data: Mapping[str, Any] | Any, *, request: Any = None
    ) -> Dict[str, Any]:
        """Flujo de login de usuario."""
        return await self._service.login(data, request=request)

    async def refresh_token(self, data: Mapping[str, Any] | Any) -> Dict[str, Any]:
        """Flujo de refresco de tokens."""
        return await self._service.refresh_tokens(data)

    # ---------------------- Stubs: logout / me ---------------------- #

    async def logout(self, refresh_token: str) -> Dict[str, Any]:
        """
        Stub de logout global. Lanza NotImplementedError para que las rutas
        respondan 501 mientras no se implemente el flujo real.
        """
        raise NotImplementedError("Logout global aún no implementado.")

    async def me(self, user_id: int | str) -> Dict[str, Any]:
        """
        Stub para devolver el perfil del usuario actual. Lanza NotImplementedError
        para que las rutas respondan 501 mientras no se implemente.
        """
        raise NotImplementedError("Endpoint 'me' aún no implementado.")


# ---------------------- Dependency wiring ---------------------- #


def get_auth_facade(
    db: AsyncSession = Depends(get_async_session),
) -> AuthFacade:
    """
    Dependencia FastAPI para obtener una instancia de AuthFacade.

    Crea un AuthService con la sesión actual y lo envuelve en AuthFacade.
    """
    service = AuthService(db=db)
    return AuthFacade(service)


__all__ = ["AuthFacade", "get_auth_facade"]

# Fin del script backend/app/modules/auth/facades/auth_facade.py