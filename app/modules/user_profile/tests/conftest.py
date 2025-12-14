# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/tests/conftest.py

Fixtures compartidas para tests del módulo de perfil de usuario.

Sistema de pago por uso con créditos prepagados (sin suscripciones).

Autor: Ixchel Beristain
Fecha: 23/10/2025
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.modules.auth.enums import UserRole, UserStatus
from app.modules.auth.models import User
from app.shared.utils.security import hash_password


@pytest.fixture
def sample_user(db_session: Session):
    """Crea un usuario de prueba en la base de datos"""
    user = User(
        user_email="test.user@example.com",
        user_password_hash=hash_password("TestPass123!"),
        user_full_name="Test User",
        user_phone="+52 55 1234 5678",
        user_is_activated=True,
        user_role=UserRole.customer,
            user_status=UserStatus.active,
        user_last_login=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def inactive_user(db_session: Session):
    """Crea un usuario inactivo de prueba"""
    user = User(
        user_email="inactive.user@example.com",
        user_password_hash=hash_password("TestPass123!"),
        user_full_name="Inactive User",
        user_is_activated=False,
        user_role=UserRole.customer,
        user_status=UserStatus.suspended,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session):
    """Crea un usuario administrador de prueba"""
    user = User(
        user_email="admin@example.com",
        user_password_hash=hash_password("AdminPass123!"),
        user_full_name="Admin User",
        user_phone="+52 55 9999 9999",
        user_is_activated=True,
        user_role=UserRole.admin,
        user_status=UserStatus.active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

# Fin del archivo backend/app/modules/user_profile/tests/conftest.py
