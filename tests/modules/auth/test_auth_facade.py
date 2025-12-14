
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/test_auth_facade.py

Tests de la fachada AuthFacade (Fase 3).

Objetivo:
- Verificar que AuthFacade delega correctamente en el servicio inyectado.
- Usar DummyService que devuelve instancias de los schemas Pydantic reales.
- No depender ya de TokenIssuer, TokenPairDict, EmailSender, RecaptchaVerifier
  que pertenecían a la arquitectura anterior.
"""

from typing import Any, Mapping

import pytest

from app.modules.auth.facades.auth_facade import AuthFacade
from app.modules.auth.schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    ActivationRequest,
    ResendActivationRequest,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
    RefreshRequest,
    TokenResponse,
    MessageResponse,
)


# --------------------------
# Dummies / Fakes de servicio
# --------------------------


class DummyService:
    """
    Servicio fake que implementa la interfaz que AuthFacade espera de AuthService.
    Devuelve instancias de los schemas Pydantic usados por las rutas.
    """

    async def register_user(self, payload: Mapping[str, Any] | Any) -> RegisterResponse:
        return RegisterResponse(
            message="registered",
            user=None,
            user_id=123,
            access_token="acc",
            token_type="bearer",
        )

    async def resend_activation_email(self, payload: Mapping[str, Any] | Any) -> MessageResponse:
        return MessageResponse(message="resent")

    async def activate_account(self, payload: Mapping[str, Any] | Any) -> MessageResponse:
        return MessageResponse(message="activated")

    async def login(self, payload: Mapping[str, Any] | Any) -> LoginResponse:
        return LoginResponse(
            message="logged in",
            access_token="acc",
            refresh_token="ref",
            token_type="bearer",
            user={
                "user_id": 123,
                "user_email": "a@b.com",
                "user_full_name": "Test User",
                "user_role": "customer",
                "user_status": "active",
            },
        )

    async def refresh_tokens(self, payload: Mapping[str, Any] | Any) -> TokenResponse:
        # Simula el contrato real de AuthService.refresh_tokens → TokenResponse
        return TokenResponse(
            access_token="new_acc",
            refresh_token="new_ref",
            token_type="bearer",
        )

    async def start_password_reset(self, payload: Mapping[str, Any] | Any) -> MessageResponse:
        return MessageResponse(message="reset email sent")

    async def confirm_password_reset(self, payload: Mapping[str, Any] | Any) -> MessageResponse:
        return MessageResponse(message="password changed")


# --------------------------
# Fixtures
# --------------------------


@pytest.fixture
def facade() -> AuthFacade:
    """
    Instancia de AuthFacade usando el DummyService en lugar de AuthService real.
    Esto nos permite probar la fachada sin depender de la BD ni de otros módulos.
    """
    return AuthFacade(auth_service=DummyService())  # type: ignore[arg-type]


# --------------------------
# Tests
# --------------------------


@pytest.mark.asyncio
async def test_register_login_refresh_and_resets(facade: AuthFacade) -> None:
    # ---------- Register ----------
    reg = RegisterRequest(
        email="a@b.com",
        password="secret123!",
        full_name="Test User",
        recaptcha_token="test-recaptcha-token",
    )
    reg_out = await facade.register_user(reg)
    assert isinstance(reg_out, RegisterResponse)
    assert reg_out.message
    assert reg_out.user_id == 123

    # ---------- Login ----------
    login = LoginRequest(
        email="a@b.com",
        password="secret123!",
        recaptcha_token="test-recaptcha-token",
    )
    login_out = await facade.login(login)
    assert isinstance(login_out, LoginResponse)
    assert login_out.access_token == "acc"
    assert login_out.refresh_token == "ref"
    assert login_out.user is not None
    assert login_out.user.user_email == "a@b.com"


    # ---------- Refresh ----------
    ref = RefreshRequest(refresh_token="ref")
    tok = await facade.refresh_token(ref)
    assert isinstance(tok, TokenResponse)
    assert tok.access_token == "new_acc"
    assert getattr(tok, "token_type", "bearer") == "bearer"


    # ---------- Forgot / Reset password ----------
    fp = PasswordResetRequest(
        email="a@b.com",
        recaptcha_token="test-recaptcha-token",
    )
    msg = await facade.forgot_password(fp)
    assert isinstance(msg, MessageResponse)
    assert "reset" in msg.message.lower()

    rp = PasswordResetConfirmRequest(token="tokentest12345", new_password="NewSecret123!")
    msg2 = await facade.reset_password(rp)
    assert isinstance(msg2, MessageResponse)
    assert "password" in msg2.message.lower()

    # ---------- Activation / Resend ----------
    act = ActivationRequest(email="a@b.com", token="tokentest12345")
    msg3 = await facade.activate_account(act)
    assert isinstance(msg3, MessageResponse)
    assert "activated" in msg3.message.lower()

    re_act = ResendActivationRequest(email="a@b.com")
    msg4 = await facade.resend_activation_email(re_act)
    assert isinstance(msg4, MessageResponse)
    assert "resent" in msg4.message.lower()


@pytest.mark.asyncio
async def test_logout_raises_not_implemented(facade: AuthFacade) -> None:
    """
    Test: logout lanza NotImplementedError (stub en Fase 3).
    Las rutas deben capturar esto y retornar 501.
    """
    with pytest.raises(NotImplementedError, match="Logout global aún no implementado"):
        await facade.logout("dummy-refresh-token")


@pytest.mark.asyncio
async def test_me_raises_not_implemented(facade: AuthFacade) -> None:
    """
    Test: me lanza NotImplementedError (stub en Fase 3).
    Las rutas deben capturar esto y retornar 501.
    """
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    
    with pytest.raises(NotImplementedError, match="Endpoint 'me' aún no implementado"):
        await facade.me(user_id=user_id)
# Fin del archivo backend/tests/modules/auth/test_auth_facade.py