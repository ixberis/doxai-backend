
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/services/test_registration_flow_service.py

Tests para RegistrationFlowService (Fase 3), alineados con la implementación real:

Casos cubiertos:
1) Falta email o password -> 400 + log_register_failed("missing_email_or_password").
2) Usuario ya existente y ACTIVO -> 409 "ya está registrado y activo" + log_register_failed("email_already_registered").
3) Usuario ya existente pero NO ACTIVO -> reenvía activación, genera access_token, log_register_success.
4) Usuario nuevo -> crea usuario, emite token de activación, envía correo, genera access_token, log_register_success.
5) IntegrityError al crear usuario -> 409 "ya está en uso" + log_register_failed("integrity_error_email_in_use").
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.modules.auth.services.registration_flow_service import RegistrationFlowService
from app.modules.auth.models.user_models import AppUser


@pytest.fixture
def base_payload():
    return {
        "email": "new@example.com",
        "password": "Secret123!",
        "full_name": "Nuevo Usuario",
        "ip_address": "127.0.0.1",
        "user_agent": "pytest",
    }


@pytest.mark.asyncio
async def test_register_user_missing_email_or_password_raises_400(base_payload):
    """Si falta email o password, se debe lanzar 400 y log_register_failed con missing_email_or_password."""
    db = AsyncMock()
    email_sender = AsyncMock()
    token_issuer = MagicMock()
    fake_user_service = AsyncMock()
    fake_activation_service = AsyncMock()
    fake_audit = MagicMock()

    service = RegistrationFlowService(
        db=db,
        email_sender=email_sender,
        token_issuer=token_issuer,
        user_service=fake_user_service,
        activation_service=fake_activation_service,
        audit_service=fake_audit,
    )

    # Caso 1: email vacío
    payload = dict(base_payload)
    payload["email"] = ""

    with pytest.raises(HTTPException) as excinfo:
        await service.register_user(payload)

    assert excinfo.value.status_code == 400
    fake_audit.log_register_failed.assert_called()
    args, kwargs = fake_audit.log_register_failed.call_args
    assert kwargs["error_message"] == "missing_email_or_password"

    fake_audit.log_register_failed.reset_mock()

    # Caso 2: password vacío
    payload2 = dict(base_payload)
    payload2["password"] = ""

    with pytest.raises(HTTPException) as excinfo2:
        await service.register_user(payload2)

    assert excinfo2.value.status_code == 400
    fake_audit.log_register_failed.assert_called()
    args2, kwargs2 = fake_audit.log_register_failed.call_args
    assert kwargs2["error_message"] == "missing_email_or_password"


@pytest.mark.asyncio
async def test_register_user_existing_active_user_raises_409(base_payload):
    """
    Si el usuario ya existe y está ACTIVO:
    - is_active(existing) -> True
    - Se lanza HTTPException 409 con mensaje de correo ya registrado y activo.
    - log_register_failed se llama con error_message=email_already_registered.
    """
    db = AsyncMock()
    email_sender = AsyncMock()
    token_issuer = MagicMock()
    fake_user_service = AsyncMock()
    fake_activation_service = AsyncMock()
    fake_audit = MagicMock()

    existing = AppUser()
    existing.user_id = 10
    existing.user_email = base_payload["email"]
    existing.user_full_name = base_payload["full_name"]

    fake_user_service.get_by_email.return_value = existing
    fake_activation_service.is_active.return_value = True

    service = RegistrationFlowService(
        db=db,
        email_sender=email_sender,
        token_issuer=token_issuer,
        user_service=fake_user_service,
        activation_service=fake_activation_service,
        audit_service=fake_audit,
    )

    with pytest.raises(HTTPException) as excinfo:
        await service.register_user(base_payload)

    assert excinfo.value.status_code == 409
    assert "ya está registrado y activo" in excinfo.value.detail

    fake_audit.log_register_failed.assert_called()
    args, kwargs = fake_audit.log_register_failed.call_args
    assert kwargs["error_message"] == "email_already_registered"
    assert kwargs["extra_data"]["user_id"] == str(existing.user_id)


@pytest.mark.asyncio
async def test_register_user_existing_inactive_user_resends_activation(base_payload, monkeypatch):
    """
    Si el usuario ya existe pero NO está activo:
    - is_active(existing) -> False
    - Se emite nuevo token de activación
    - Se envía correo de activación
    - Se genera access_token
    - Se registra log_register_success
    - Se devuelve mensaje de reenvío de activación.
    """
    db = AsyncMock()
    email_sender = AsyncMock()
    token_issuer = MagicMock()
    token_issuer.create_access_token.return_value = "acc-token-resend"

    fake_user_service = AsyncMock()
    fake_activation_service = AsyncMock()
    fake_audit = MagicMock()

    existing = AppUser()
    existing.user_id = 11
    existing.user_email = base_payload["email"]
    existing.user_full_name = base_payload["full_name"]

    fake_user_service.get_by_email.return_value = existing
    fake_activation_service.is_active.return_value = False
    fake_activation_service.issue_activation_token.return_value = "new-activation-token"

    import app.modules.auth.services.registration_flow_service as rf_mod

    send_act_mock = AsyncMock()
    monkeypatch.setattr(rf_mod, "send_activation_email_or_raise", send_act_mock)

    service = RegistrationFlowService(
        db=db,
        email_sender=email_sender,
        token_issuer=token_issuer,
        user_service=fake_user_service,
        activation_service=fake_activation_service,
        audit_service=fake_audit,
    )

    result = await service.register_user(base_payload)

    # Verificaciones
    fake_activation_service.issue_activation_token.assert_awaited_once_with(user_id=existing.user_id)
    send_act_mock.assert_awaited_once()
    token_issuer.create_access_token.assert_called_once_with(sub=str(existing.user_id))
    fake_audit.log_register_success.assert_called_once()

    assert result["user_id"] == existing.user_id
    assert result["access_token"] == "acc-token-resend"
    assert "Correo de activación reenviado" in result["message"]


@pytest.mark.asyncio
async def test_register_user_new_user_success(base_payload, monkeypatch):
    """
    Caso de usuario nuevo:
    - get_by_email -> None
    - UserService.add crea usuario
    - Se emite token de activación y se envía correo
    - Se genera access_token
    - Se registra log_register_success
    - Se devuelve mensaje de éxito y user_id/access_token.
    """
    db = AsyncMock()
    email_sender = AsyncMock()
    token_issuer = MagicMock()
    token_issuer.create_access_token.return_value = "acc-token-new"

    fake_user_service = AsyncMock()
    fake_activation_service = AsyncMock()
    fake_audit = MagicMock()

    fake_user_service.get_by_email.return_value = None

    created = AppUser()
    created.user_id = 12
    created.user_email = base_payload["email"]
    created.user_full_name = base_payload["full_name"]

    fake_user_service.add.return_value = created
    fake_activation_service.issue_activation_token.return_value = "activation-token"

    import app.modules.auth.services.registration_flow_service as rf_mod

    send_act_mock = AsyncMock()
    monkeypatch.setattr(rf_mod, "send_activation_email_or_raise", send_act_mock)

    service = RegistrationFlowService(
        db=db,
        email_sender=email_sender,
        token_issuer=token_issuer,
        user_service=fake_user_service,
        activation_service=fake_activation_service,
        audit_service=fake_audit,
    )

    result = await service.register_user(base_payload)

    fake_user_service.add.assert_awaited_once()
    fake_activation_service.issue_activation_token.assert_awaited_once_with(user_id=created.user_id)
    send_act_mock.assert_awaited_once()
    token_issuer.create_access_token.assert_called_once_with(sub=str(created.user_id))
    fake_audit.log_register_success.assert_called_once()

    assert result["user_id"] == created.user_id
    assert result["access_token"] == "acc-token-new"
    assert "Usuario registrado" in result["message"]


@pytest.mark.asyncio
async def test_register_user_integrity_error_maps_to_409(base_payload):
    """
    Si al crear usuario se lanza IntegrityError:
    - Se registra log_register_failed con integrity_error_email_in_use
    - Se lanza HTTPException 409 con mensaje de correo ya en uso.
    """
    db = AsyncMock()
    email_sender = AsyncMock()
    token_issuer = MagicMock()

    fake_user_service = AsyncMock()
    fake_activation_service = AsyncMock()
    fake_audit = MagicMock()

    fake_user_service.get_by_email.return_value = None
    fake_user_service.add.side_effect = IntegrityError("dup", params={}, orig=None)

    service = RegistrationFlowService(
        db=db,
        email_sender=email_sender,
        token_issuer=token_issuer,
        user_service=fake_user_service,
        activation_service=fake_activation_service,
        audit_service=fake_audit,
    )

    with pytest.raises(HTTPException) as excinfo:
        await service.register_user(base_payload)

    assert excinfo.value.status_code == 409
    assert "ya está en uso" in excinfo.value.detail
    fake_audit.log_register_failed.assert_called()
    args, kwargs = fake_audit.log_register_failed.call_args
    assert kwargs["error_message"] == "integrity_error_email_in_use"

# Fin del archivo backend/tests/modules/auth/services/test_registration_flow_service.py
