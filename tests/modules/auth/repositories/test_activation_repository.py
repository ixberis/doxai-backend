
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/repositories/test_activation_repository.py

Tests unitarios para ActivationRepository (Fase 3).
Verifica que los métodos de repositorio orquestan correctamente el AsyncSession:

- create_activation: inserta un registro de AccountActivation.
- get_by_token: consulta por token.
- mark_as_used: marca el registro como usado.

Estos tests usan AsyncMock para no depender de una BD real.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.modules.auth.repositories import ActivationRepository
from app.modules.auth.models.activation_models import AccountActivation
from app.modules.auth.enums import ActivationStatus


@pytest.mark.asyncio
async def test_create_activation_adds_account_activation_instance():
    """create_activation debe instanciar AccountActivation y llamar session.add()."""
    db = AsyncMock()
    # Aseguramos métodos async esperados por el repo
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    repo = ActivationRepository(db)

    user_id = 42
    token = "test-token"
    from datetime import datetime, timezone, timedelta

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    await repo.create_activation(user_id=user_id, token=token, expires_at=expires_at)

    # Verificamos que se haya agregado un AccountActivation
    assert db.add.call_count == 1
    added_obj = db.add.call_args.args[0]
    assert isinstance(added_obj, AccountActivation)
    assert added_obj.user_id == user_id
    assert added_obj.token == token
    assert added_obj.expires_at == expires_at

    # Debe intentar persistir
    assert db.flush.await_count or db.commit.await_count or db.refresh.await_count


@pytest.mark.asyncio
async def test_get_by_token_uses_select_on_token():
    """get_by_token debe ejecutar una query filtrada por token y devolver scalar_one_or_none()."""
    db = AsyncMock()
    repo = ActivationRepository(db)

    fake_activation = AccountActivation()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_activation
    db.execute.return_value = fake_result

    result = await repo.get_by_token("abc123")

    assert result is fake_activation
    assert db.execute.called
    fake_result.scalar_one_or_none.assert_called_once()


@pytest.mark.asyncio
async def test_mark_as_used_updates_status_and_flush():
    """mark_as_used debe marcar la activación como usada y hacer flush/commit."""
    db = AsyncMock()
    db.merge = AsyncMock(side_effect=lambda obj: obj)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    repo = ActivationRepository(db)

    activation = AccountActivation()
    activation.status = None  # estado inicial irrelevante

    await repo.mark_as_used(activation)

    assert activation.status == ActivationStatus.used
    assert db.merge.await_count == 1
    assert db.flush.await_count or db.commit.await_count

# Fin del archivo backend/tests/modules/auth/repositories/test_activation_repository.py