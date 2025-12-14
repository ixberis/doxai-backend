
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/services/test_activation_service_credits.py

Tests específicos de ActivationService relacionados con créditos de bienvenida.

- Cuando ensure_welcome_credits devuelve True, el resultado incluye credits_assigned == welcome_credits.
- Cuando ensure_welcome_credits devuelve False o lanza excepción, la activación sigue siendo
  exitosa pero credits_assigned = 0.

Se mockean ActivationRepository, UserRepository y CreditService para centrarse en la lógica
de ActivationService, sin tocar la BD real.
"""

import pytest
from unittest.mock import AsyncMock

from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.enums import ActivationStatus
from app.modules.auth.models.activation_models import AccountActivation
from app.modules.auth.models.user_models import AppUser


def _make_fake_activation(user_id: int, token: str = "dummy") -> AccountActivation:
    act = AccountActivation()
    act.id = 1
    act.user_id = user_id
    act.token = token
    # Estado inicial irrelevante, sólo que no sea usado/expirado
    act.status = None
    from datetime import datetime, timedelta, timezone

    act.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    return act


def _make_fake_user(user_id: int) -> AppUser:
    user = AppUser()
    user.user_id = user_id
    user.user_email = f"user{user_id}@example.com"
    user.user_full_name = f"User {user_id}"
    # ActivationService se encarga de ajustar user_status / user_is_activated
    user.user_status = None
    user.user_is_activated = False
    return user


@pytest.mark.asyncio
async def test_activate_account_assigns_welcome_credits_when_credit_service_returns_true(monkeypatch):
    """Cuando ensure_welcome_credits devuelve True, se deben asignar créditos > 0."""
    db = AsyncMock()
    service = ActivationService(db, welcome_credits=5)

    fake_activation = _make_fake_activation(user_id=123)
    fake_user = _make_fake_user(user_id=123)

    service.activation_repo = AsyncMock()
    service.activation_repo.get_by_token.return_value = fake_activation
    service.activation_repo.mark_as_used = AsyncMock()

    service.user_repo = AsyncMock()
    service.user_repo.get_by_id.return_value = fake_user
    service.user_repo.save = AsyncMock()

    fake_credit_service = AsyncMock()
    fake_credit_service.ensure_welcome_credits.return_value = True
    service.credit_service = fake_credit_service

    result = await service.activate_account("dummy-token")

    assert result["code"] == "ACCOUNT_ACTIVATED"
    assert result["credits_assigned"] == 5
    assert "warnings" not in result  # No debe tener warnings
    fake_credit_service.ensure_welcome_credits.assert_called_once_with(user_id=123, welcome_credits=5)


@pytest.mark.asyncio
async def test_activate_account_no_credits_when_credit_service_returns_false(monkeypatch):
    """Si ensure_welcome_credits devuelve False, credits_assigned debe ser 0."""
    db = AsyncMock()
    service = ActivationService(db, welcome_credits=5)

    fake_activation = _make_fake_activation(user_id=456)
    fake_user = _make_fake_user(user_id=456)

    service.activation_repo = AsyncMock()
    service.activation_repo.get_by_token.return_value = fake_activation
    service.activation_repo.mark_as_used = AsyncMock()

    service.user_repo = AsyncMock()
    service.user_repo.get_by_id.return_value = fake_user
    service.user_repo.save = AsyncMock()

    fake_credit_service = AsyncMock()
    fake_credit_service.ensure_welcome_credits.return_value = False
    service.credit_service = fake_credit_service

    result = await service.activate_account("dummy-token")

    assert result["code"] == "ACCOUNT_ACTIVATED"
    assert result["credits_assigned"] == 0
    fake_credit_service.ensure_welcome_credits.assert_called_once()


@pytest.mark.asyncio
async def test_activate_account_handles_credit_service_exception(monkeypatch, caplog):
    """
    Si CreditService lanza excepción, la activación no debe fallar:
    - code = ACCOUNT_ACTIVATED
    - credits_assigned = 0
    - warnings incluye 'welcome_credits_failed'
    - se loguea el error
    """
    db = AsyncMock()
    service = ActivationService(db, welcome_credits=5)

    fake_activation = _make_fake_activation(user_id=789)
    fake_user = _make_fake_user(user_id=789)

    service.activation_repo = AsyncMock()
    service.activation_repo.get_by_token.return_value = fake_activation
    service.activation_repo.mark_as_used = AsyncMock()

    service.user_repo = AsyncMock()
    service.user_repo.get_by_id.return_value = fake_user
    service.user_repo.save = AsyncMock()

    fake_credit_service = AsyncMock()
    fake_credit_service.ensure_welcome_credits.side_effect = RuntimeError("boom")
    service.credit_service = fake_credit_service

    with caplog.at_level("ERROR"):
        result = await service.activate_account("dummy-token")

    assert result["code"] == "ACCOUNT_ACTIVATED"
    assert result["credits_assigned"] == 0
    assert "warnings" in result
    assert "welcome_credits_failed" in result["warnings"]
    assert any("Error asignando créditos de bienvenida" in rec.message for rec in caplog.records)

# Fin del archivo backend/tests/modules/auth/services/test_activation_service_credits.py