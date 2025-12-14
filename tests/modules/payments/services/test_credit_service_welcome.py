
# -*- coding: utf-8 -*-
"""
backend/tests/modules/payments/services/test_credit_service_welcome.py

Tests para ensure_welcome_credits en CreditService.
Verifica:
- Idempotencia (dos llamadas no duplican créditos)
- Creación correcta de transacción
- Manejo de IntegrityError como idempotencia

Autor: Ixchel Beristain
Fecha: 2025-12-13
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError

from app.modules.payments.services.credit_service import CreditService


class MockNestedTransactionSuccess:
    """Mock de async context manager para begin_nested exitoso."""
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


@pytest.mark.asyncio
async def test_ensure_welcome_credits_first_time_creates_credits():
    """Primera llamada debe crear créditos y retornar True."""
    mock_db = AsyncMock()
    service = CreditService(mock_db)
    
    # Mock del repo: no existe transacción previa
    service.credit_repo = AsyncMock()
    service.credit_repo.get_by_idempotency_key.return_value = None
    service.credit_repo.compute_balance.return_value = 0
    
    # Mock del session.add, flush y begin_nested
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.begin_nested = MagicMock(return_value=MockNestedTransactionSuccess())
    
    result = await service.ensure_welcome_credits(user_id=123, welcome_credits=5)
    
    assert result is True
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    service.credit_repo.get_by_idempotency_key.assert_called_once_with(
        mock_db, 123, "welcome_credits"
    )


@pytest.mark.asyncio
async def test_ensure_welcome_credits_idempotent_returns_false():
    """Segunda llamada (ya existe) debe retornar False sin crear nada."""
    mock_db = AsyncMock()
    service = CreditService(mock_db)
    
    # Mock del repo: ya existe transacción
    existing_tx = MagicMock()
    existing_tx.id = 999
    service.credit_repo = AsyncMock()
    service.credit_repo.get_by_idempotency_key.return_value = existing_tx
    
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.begin_nested = MagicMock(return_value=MockNestedTransactionSuccess())
    
    result = await service.ensure_welcome_credits(user_id=123, welcome_credits=5)
    
    assert result is False
    # No debe agregar nada (fast-path por idempotencia)
    mock_db.add.assert_not_called()
    mock_db.flush.assert_not_called()
    mock_db.begin_nested.assert_not_called()  # Ni siquiera entra al savepoint


@pytest.mark.asyncio
async def test_ensure_welcome_credits_integrity_error_with_savepoint():
    """
    Si hay IntegrityError dentro del savepoint (race condition), 
    retornar False sin afectar la transacción exterior.
    """
    mock_db = AsyncMock()
    service = CreditService(mock_db)
    
    service.credit_repo = AsyncMock()
    service.credit_repo.get_by_idempotency_key.return_value = None
    service.credit_repo.compute_balance.return_value = 0
    
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    
    # Simular que begin_nested() lanza IntegrityError al salir del context
    class MockNestedTransactionIntegrityError:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            # Simular IntegrityError al hacer commit del savepoint
            raise IntegrityError("dup", None, None)
    
    mock_db.begin_nested = MagicMock(return_value=MockNestedTransactionIntegrityError())
    
    result = await service.ensure_welcome_credits(user_id=123, welcome_credits=5)
    
    # Debe retornar False sin propagar la excepción
    assert result is False
    # NO debe llamar rollback en la session principal
    mock_db.rollback.assert_not_called() if hasattr(mock_db, 'rollback') else None


@pytest.mark.asyncio
async def test_ensure_welcome_credits_without_session_raises():
    """Sin session debe lanzar ValueError."""
    from app.modules.payments.repositories.credit_transaction_repository import (
        CreditTransactionRepository,
    )
    
    # Pasar repo en lugar de session
    repo = CreditTransactionRepository()
    service = CreditService(repo)
    
    with pytest.raises(ValueError, match="requires AsyncSession"):
        await service.ensure_welcome_credits(user_id=123, welcome_credits=5)


@pytest.mark.asyncio
async def test_ensure_welcome_credits_savepoint_success():
    """Verificar que el savepoint se usa correctamente en caso de éxito."""
    mock_db = AsyncMock()
    service = CreditService(mock_db)
    
    service.credit_repo = AsyncMock()
    service.credit_repo.get_by_idempotency_key.return_value = None
    service.credit_repo.compute_balance.return_value = 10
    
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.begin_nested = MagicMock(return_value=MockNestedTransactionSuccess())
    
    result = await service.ensure_welcome_credits(user_id=456, welcome_credits=10)
    
    assert result is True
    mock_db.begin_nested.assert_called_once()
    mock_db.add.assert_called_once()


# Fin del archivo backend/tests/modules/payments/services/test_credit_service_welcome.py
