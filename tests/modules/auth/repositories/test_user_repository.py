
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/repositories/test_user_repository.py

Tests unitarios para UserRepository (Fase 3).

Se verifica que:
- get_by_id delega correctamente a AsyncSession.execute y procesa scalar_one_or_none().
- get_by_email hace lo mismo con el filtro de email.
- save intenta persistir el objeto (merge + flush/commit) y lo retorna.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.modules.auth.repositories import UserRepository
from app.modules.auth.models.user_models import AppUser


@pytest.mark.asyncio
async def test_get_by_id_returns_user_from_scalar_one_or_none():
    db = AsyncMock()
    repo = UserRepository(db)

    fake_user = AppUser()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_user
    db.execute.return_value = fake_result

    result = await repo.get_by_id(123)

    assert result is fake_user
    assert db.execute.called
    fake_result.scalar_one_or_none.assert_called_once()


@pytest.mark.asyncio
async def test_get_by_email_returns_user_from_scalar_one_or_none():
    db = AsyncMock()
    repo = UserRepository(db)

    fake_user = AppUser()
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = fake_user
    db.execute.return_value = fake_result

    result = await repo.get_by_email("test@example.com")

    assert result is fake_user
    assert db.execute.called
    fake_result.scalar_one_or_none.assert_called_once()


@pytest.mark.asyncio
async def test_save_adds_user_and_flush_or_commit():
    db = AsyncMock()
    db.merge = AsyncMock(side_effect=lambda obj: obj)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    repo = UserRepository(db)

    user = AppUser()
    saved = await repo.save(user)

    assert saved is user
    # Verificamos que se intente persistir
    assert db.merge.await_count == 1
    assert db.flush.await_count or db.commit.await_count

# Fin del archivo backend/tests/modules/auth/repositories/test_user_repository.py