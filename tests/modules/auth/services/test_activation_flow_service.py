
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/services/test_activation_flow_service.py

Tests para ActivationFlowService (orquestador del flujo de activación).

Se valida que:
- Propaga correctamente code/message/credits_assigned de ActivationService.
- Cuando se proporciona email, obtiene el usuario y manda correo de bienvenida.
- No envía correo si el código no es ACCOUNT_ACTIVATED o si no hay email.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.modules.auth.services.activation_flow_service import ActivationFlowService
from app.modules.auth.models.user_models import AppUser


@pytest.mark.asyncio
async def test_activate_account_propagates_result_and_sends_welcome_email(monkeypatch):
    """Flujo feliz: cuenta activada, se envía correo y se propagan créditos."""
    db = AsyncMock()
    email_sender = AsyncMock()

    # Mocks de servicios internos
    fake_activation_service = AsyncMock()
    fake_activation_service.activate_account.return_value = {
        "code": "ACCOUNT_ACTIVATED",
        "message": "ok",
        "credits_assigned": 5,
    }

    fake_user_service = AsyncMock()
    fake_user = AppUser()
    fake_user.user_id = 11
    fake_user.user_email = "user@example.com"
    fake_user.user_full_name = "Usuario Ejemplo"
    fake_user_service.get_by_email.return_value = fake_user

    fake_audit = MagicMock()

    # Parchear dependencias dentro del módulo
    from app.modules.auth import services as auth_services_pkg  # type: ignore

    # ActivationFlowService importa ActivationService, UserService, AuditService desde
    # app.modules.auth.services.activation_flow_service; hacemos monkeypatch allí.
    import app.modules.auth.services.activation_flow_service as af_mod

    monkeypatch.setattr(af_mod, "ActivationService", lambda db: fake_activation_service)
    monkeypatch.setattr(af_mod, "UserService", MagicMock(with_session=lambda db: fake_user_service))
    monkeypatch.setattr(af_mod, "AuditService", fake_audit)

    send_welcome_mock = AsyncMock()
    monkeypatch.setattr(af_mod, "send_welcome_email_safely", send_welcome_mock)

    flow = ActivationFlowService(db=db, email_sender=email_sender)

    payload = {"token": "dummy-token", "email": "user@example.com"}

    result = await flow.activate_account(payload)

    assert result["code"] == "ACCOUNT_ACTIVATED"
    assert result["message"] == "ok"
    assert result["credits_assigned"] == 5

    fake_activation_service.activate_account.assert_called_once_with("dummy-token")
    fake_user_service.get_by_email.assert_called_once_with("user@example.com")

    send_welcome_mock.assert_awaited_once()
    args, kwargs = send_welcome_mock.call_args
    assert kwargs["email"] == "user@example.com"
    assert kwargs["full_name"] == "Usuario Ejemplo"
    assert kwargs["credits_assigned"] == 5

    fake_audit.log_activation_success.assert_called_once()


@pytest.mark.asyncio
async def test_activate_account_does_not_send_welcome_without_email(monkeypatch):
    """Si no se proporciona email, no debe dispararse el correo de bienvenida."""
    db = AsyncMock()
    email_sender = AsyncMock()

    fake_activation_service = AsyncMock()
    fake_activation_service.activate_account.return_value = {
        "code": "ACCOUNT_ACTIVATED",
        "message": "ok",
        "credits_assigned": 5,
    }

    fake_user_service = AsyncMock()
    fake_audit = MagicMock()

    import app.modules.auth.services.activation_flow_service as af_mod

    monkeypatch.setattr(af_mod, "ActivationService", lambda db: fake_activation_service)
    monkeypatch.setattr(af_mod, "UserService", MagicMock(with_session=lambda db: fake_user_service))
    monkeypatch.setattr(af_mod, "AuditService", fake_audit)

    send_welcome_mock = AsyncMock()
    monkeypatch.setattr(af_mod, "send_welcome_email_safely", send_welcome_mock)

    flow = ActivationFlowService(db=db, email_sender=email_sender)

    payload = {"token": "dummy-token"}  # sin email
    result = await flow.activate_account(payload)

    assert result["code"] == "ACCOUNT_ACTIVATED"
    send_welcome_mock.assert_not_called()
    fake_user_service.get_by_email.assert_not_called()
    fake_audit.log_activation_success.assert_not_called()


@pytest.mark.asyncio
async def test_resend_activation_handles_already_active_user(monkeypatch):
    """resend_activation debe devolver mensaje de cuenta activa si is_active=True."""
    db = AsyncMock()
    email_sender = AsyncMock()

    fake_activation_service = AsyncMock()
    fake_activation_service.is_active.return_value = True

    fake_user_service = AsyncMock()
    fake_user = AppUser()
    fake_user.user_id = 99
    fake_user.user_email = "user99@example.com"
    fake_user.user_full_name = "User 99"
    fake_user_service.get_by_email.return_value = fake_user

    fake_audit = MagicMock()

    import app.modules.auth.services.activation_flow_service as af_mod

    monkeypatch.setattr(af_mod, "ActivationService", lambda db: fake_activation_service)
    monkeypatch.setattr(af_mod, "UserService", MagicMock(with_session=lambda db: fake_user_service))
    monkeypatch.setattr(af_mod, "AuditService", fake_audit)

    send_activation_mock = AsyncMock()
    monkeypatch.setattr(af_mod, "send_activation_email_or_raise", send_activation_mock)

    flow = ActivationFlowService(db=db, email_sender=email_sender)

    result = await flow.resend_activation({"email": "user99@example.com"})

    assert "activa" in result["message"].lower()
    fake_activation_service.is_active.assert_awaited()
    send_activation_mock.assert_not_awaited()
    fake_audit.log_activation_resend.assert_not_called()