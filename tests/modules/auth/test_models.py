# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/tests/test_models.py

Tests unitarios para modelos ORM del módulo Auth.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from datetime import datetime, timezone, timedelta

from app.modules.auth.models.user_models import User
from app.modules.auth.models.activation_models import AccountActivation
from app.modules.auth.models.password_reset_models import PasswordReset
from app.modules.auth.enums import UserRole, UserStatus, ActivationStatus


class TestUserModel:
    """Tests para el modelo User"""
    
    def test_user_creation(self):
        """Test: Crear un usuario con campos mínimos requeridos"""
        user = User(
            user_email="test@example.com",
            user_password_hash="hashed_password",
            user_full_name="Test User",
            user_role=UserRole.customer,
            user_status=UserStatus.not_active,
        )
        
        assert user.user_email == "test@example.com"
        assert user.user_full_name == "Test User"
        assert user.user_role == UserRole.customer
        # user_is_activated tiene default "false" (string) en DB, no bool
        # Para test de modelo sin DB, no podemos asumir el default
    
    def test_user_repr(self):
        """Test: __repr__ retorna representación legible"""
        user = User(
            user_email="test@example.com",
            user_password_hash="hash",
            user_full_name="Test User",
        )
        
        repr_str = repr(user)
        assert "User" in repr_str or "AppUser" in repr_str
        assert "test@example.com" in repr_str


class TestAccountActivationModel:
    """Tests para el modelo AccountActivation"""
    
    def test_activation_creation(self):
        """Test: Crear un registro de activación"""
        user_id = 123
        expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        activation = AccountActivation(
            user_id=user_id,
            token="test-token-123",
            expires_at=expires_at,
            status=ActivationStatus.sent,
        )
        
        assert activation.user_id == user_id
        assert activation.token == "test-token-123"
        assert activation.status == ActivationStatus.sent
        assert activation.consumed_at is None
    
    def test_activation_status_values(self):
        """Test: Valores de status disponibles"""
        user_id = 456
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        # Test sent status
        activation_sent = AccountActivation(
            user_id=user_id,
            token="token-sent",
            expires_at=expires_at,
            status=ActivationStatus.sent,
        )
        assert activation_sent.status == ActivationStatus.sent
        
        # Test used status
        activation_used = AccountActivation(
            user_id=user_id,
            token="token-used",
            expires_at=expires_at,
            status=ActivationStatus.used,
        )
        assert activation_used.status == ActivationStatus.used
        
        # Test expired status
        activation_expired = AccountActivation(
            user_id=user_id,
            token="token-expired",
            expires_at=expires_at,
            status=ActivationStatus.expired,
        )
        assert activation_expired.status == ActivationStatus.expired


class TestPasswordResetModel:
    """Tests para el modelo PasswordReset"""
    
    def test_password_reset_creation(self):
        """Test: Crear un registro de reset de contraseña"""
        user_id = 789
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reset = PasswordReset(
            user_id=user_id,
            token="reset-token-456",
            expires_at=expires_at,
        )
        
        assert reset.user_id == user_id
        assert reset.token == "reset-token-456"
        assert reset.expires_at == expires_at
        assert reset.used_at is None
    
    def test_password_reset_used_at_tracking(self):
        """Test: Tracking de cuándo se usó el token"""
        user_id = 101
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reset = PasswordReset(
            user_id=user_id,
            token="token",
            expires_at=expires_at,
        )
        
        # Inicialmente no usado
        assert reset.used_at is None
        
        # Marcar como usado
        now = datetime.now(timezone.utc)
        reset.used_at = now
        
        assert reset.used_at is not None
        assert isinstance(reset.used_at, datetime)
        assert reset.used_at == now
