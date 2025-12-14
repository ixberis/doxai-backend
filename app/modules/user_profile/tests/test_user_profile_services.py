# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/tests/test_services.py

Tests para los servicios del módulo de perfil de usuario.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from uuid import uuid4
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.modules.user_profile.services import UserProfileService
from app.modules.user_profile.schemas import UserProfileUpdateRequest
from app.modules.auth.enums import UserRole, UserStatus

# Alias para compatibilidad con tests
SubscriptionStatus = UserStatus


class TestUserProfileService:
    """Tests para UserProfileService"""

    def test_get_user_by_id(self, db_session: Session, sample_user):
        """Test: obtener usuario por ID"""
        service = UserProfileService(db_session)
        
        user = service.get_user_by_id(user_id=sample_user.user_id)
        
        assert user is not None
        assert user.user_id == sample_user.user_id
        assert user.user_email == sample_user.user_email

    def test_get_user_by_id_not_found(self, db_session: Session):
        """Test: usuario no encontrado por ID"""
        service = UserProfileService(db_session)
        
        user = service.get_user_by_id(user_id=uuid4())
        
        assert user is None

    def test_get_user_by_email(self, db_session: Session, sample_user):
        """Test: obtener usuario por email"""
        service = UserProfileService(db_session)
        
        user = service.get_user_by_email(email=sample_user.user_email)
        
        assert user is not None
        assert user.user_email == sample_user.user_email

    def test_get_user_by_email_case_insensitive(self, db_session: Session, sample_user):
        """Test: búsqueda por email case-insensitive"""
        service = UserProfileService(db_session)
        
        user = service.get_user_by_email(email=sample_user.user_email.upper())
        
        assert user is not None
        assert user.user_email == sample_user.user_email

    def test_get_profile_by_id(self, db_session: Session, sample_user):
        """Test: obtener perfil completo por ID"""
        service = UserProfileService(db_session)
        
        profile = service.get_profile_by_id(user_id=sample_user.user_id)
        
        assert profile.user_id == sample_user.user_id
        assert profile.user_email == sample_user.user_email
        assert profile.user_full_name == sample_user.user_full_name
        assert profile.user_role == sample_user.user_role

    def test_get_profile_by_id_not_found(self, db_session: Session):
        """Test: perfil no encontrado por ID"""
        service = UserProfileService(db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            service.get_profile_by_id(user_id=uuid4())
        
        assert exc_info.value.status_code == 404

    def test_get_profile_by_email(self, db_session: Session, sample_user):
        """Test: obtener perfil completo por email"""
        service = UserProfileService(db_session)
        
        profile = service.get_profile_by_email(email=sample_user.user_email)
        
        assert profile.user_email == sample_user.user_email
        assert profile.user_full_name == sample_user.user_full_name

    def test_update_profile_name(self, db_session: Session, sample_user):
        """Test: actualizar nombre del usuario"""
        service = UserProfileService(db_session)
        
        update_data = UserProfileUpdateRequest(
            user_full_name="Updated Name"
        )
        
        response = service.update_profile(
            user_id=sample_user.user_id,
            profile_data=update_data
        )
        
        assert response.success is True
        assert response.user.user_full_name == "Updated Name"
        assert response.user.user_email == sample_user.user_email

    def test_update_profile_phone(self, db_session: Session, sample_user):
        """Test: actualizar teléfono del usuario"""
        service = UserProfileService(db_session)
        
        update_data = UserProfileUpdateRequest(
            user_phone="+52 55 9999 8888"
        )
        
        response = service.update_profile(
            user_id=sample_user.user_id,
            profile_data=update_data
        )
        
        assert response.success is True
        assert response.user.user_phone == "+52 55 9999 8888"

    def test_update_profile_both_fields(self, db_session: Session, sample_user):
        """Test: actualizar nombre y teléfono simultáneamente"""
        service = UserProfileService(db_session)
        
        update_data = UserProfileUpdateRequest(
            user_full_name="New Full Name",
            user_phone="+1 555 123 4567"
        )
        
        response = service.update_profile(
            user_id=sample_user.user_id,
            profile_data=update_data
        )
        
        assert response.success is True
        assert response.user.user_full_name == "New Full Name"
        assert response.user.user_phone == "+1 555 123 4567"

    def test_update_profile_user_not_found(self, db_session: Session):
        """Test: actualizar perfil de usuario inexistente"""
        service = UserProfileService(db_session)
        
        update_data = UserProfileUpdateRequest(
            user_full_name="Should Fail"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            service.update_profile(
                user_id=uuid4(),
                profile_data=update_data
            )
        
        assert exc_info.value.status_code == 404

    def test_get_subscription_status(self, db_session: Session, sample_user):
        """Test: obtener estado de suscripción"""
        service = UserProfileService(db_session)
        
        subscription = service.get_subscription_status(user_id=sample_user.user_id)
        
        assert subscription.user_id == sample_user.user_id
        assert subscription.subscription_status == sample_user.user_subscription_status
        assert subscription.subscription_period_end == sample_user.subscription_period_end

    def test_get_subscription_status_user_not_found(self, db_session: Session):
        """Test: estado de suscripción de usuario inexistente"""
        service = UserProfileService(db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            service.get_subscription_status(user_id=uuid4())
        
        assert exc_info.value.status_code == 404

    def test_update_last_login(self, db_session: Session, sample_user):
        """Test: actualizar timestamp de último login"""
        service = UserProfileService(db_session)
        
        original_login = sample_user.user_last_login
        
        service.update_last_login(user_id=sample_user.user_id)
        
        db_session.refresh(sample_user)
        assert sample_user.user_last_login > original_login
