# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/tests/test_services.py

Tests unitarios para servicios del módulo Auth.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta

from app.modules.auth.services.activation_service import ActivationService
from app.modules.auth.models.user_models import User
from app.modules.auth.models.activation_models import AccountActivation
from app.modules.auth.enums import UserStatus, ActivationStatus


class TestActivationService:
    """Tests para el servicio de activación"""
    
    @pytest.mark.asyncio
    async def test_issue_activation_token_success(self, db_session):
        """Test: Emitir token de activación exitosamente usando issue_activation_token"""
        service = ActivationService(db_session)
        user_id = 123
        
        # Mock del repositorio
        mock_activation_repo = AsyncMock()
        service.activation_repo = mock_activation_repo
        
        # Token factory que retorna un token predecible
        def fake_token_factory():
            return "test_token_abc123"
        
        token = await service.issue_activation_token(
            user_id=user_id, 
            ttl_minutes=1440,
            token_factory=fake_token_factory
        )
        
        assert token is not None
        assert token == "test_token_abc123"
        mock_activation_repo.create_activation.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_is_active_returns_true_for_activated_user(self, db_session):
        """Test: is_active retorna True para usuario activado"""
        service = ActivationService(db_session)
        
        user = MagicMock(spec=User)
        user.user_is_activated = True
        
        result = await service.is_active(user)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_is_active_returns_false_for_inactive_user(self, db_session):
        """Test: is_active retorna False para usuario inactivo"""
        service = ActivationService(db_session)
        
        user = MagicMock(spec=User)
        user.user_is_activated = False
        user.is_active = False
        
        result = await service.is_active(user)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_activate_account_with_invalid_token(self, db_session):
        """Test: Activar cuenta con token inválido"""
        service = ActivationService(db_session)
        
        # Mock execute que no retorna resultados
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await service.activate_account(token="invalid.token")
        
        assert result["code"] == "TOKEN_INVALID"
        assert "Token de activación inválido" in result["message"]

    
    @pytest.mark.asyncio
    async def test_activate_account_with_expired_token(self, db_session):
        """Test: Activar cuenta con token expirado"""
        service = ActivationService(db_session)
        
        # Mock de token expirado
        expired_activation = MagicMock(spec=AccountActivation)
        expired_activation.status = ActivationStatus.expired
        expired_activation.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_activation.id = 1
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expired_activation
        db_session.execute = AsyncMock(return_value=mock_result)
        db_session.flush = AsyncMock()
        
        result = await service.activate_account(token="expired.token")
        
        assert result["code"] == "TOKEN_EXPIRED"
        assert "expirado" in result["message"]


# Fixtures para tests
@pytest.fixture
def db_session():
    """Mock de sesión de base de datos"""
    session = MagicMock()
    session.query = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session
