# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/tests/conftest.py

Configuración de fixtures para tests del módulo Auth.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    """
    Fixture: Mock de sesión de base de datos SQLAlchemy.
    """
    session = MagicMock(spec=Session)
    session.query = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    return session


@pytest.fixture
def mock_user():
    """
    Fixture: Usuario de prueba con datos básicos.
    """
    from uuid import uuid4
    from app.modules.auth.models import User
    from app.modules.auth.enums import UserRole, UserStatus
    
    user = User(
        user_id=uuid4(),
        user_email="test@example.com",
        user_password_hash="hashed_password",
        user_full_name="Test User",
        user_role=UserRole.customer,
        user_status=UserStatus.not_active,
        user_is_activated=False,
    )
    return user


@pytest.fixture
def mock_activation_token():
    """
    Fixture: Token de activación de prueba.
    """
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token"


@pytest.fixture
def mock_reset_token():
    """
    Fixture: Token de reset de contraseña de prueba.
    """
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.reset.token"


@pytest.fixture
def mock_db_dependency():
    """
    Fixture: Mock de la dependencia get_db para evitar conexiones reales en tests de rutas.
    """
    from unittest.mock import AsyncMock
    
    async def mock_get_db():
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()
        yield mock_session
    
    return mock_get_db
