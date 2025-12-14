# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/tests/test_routes.py

Tests unitarios para rutas del módulo Auth.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.modules.auth.routes import get_auth_routers
from app.shared.database.database import get_db


# Configurar app de prueba con mock de DB
app = FastAPI()
for router in get_auth_routers():
    app.include_router(router)

# Mock global de get_db para evitar conexiones reales
async def mock_get_db():
    mock_session = MagicMock()
    # Mock de execute que devuelve un resultado con métodos que NO son async
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)
    mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    mock_result.fetchall = MagicMock(return_value=[])
    
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    yield mock_session

app.dependency_overrides[get_db] = mock_get_db
client = TestClient(app)


class TestRegisterRoute:
    """Tests para POST /auth/register"""
    
    @pytest.mark.asyncio
    async def test_register_success(self):
        """Test: Registro exitoso de usuario"""
        # Mock del facade usando dependency_overrides
        mock_facade = MagicMock()
        mock_facade.register_user = AsyncMock(return_value={
            "message": "Usuario registrado exitosamente",
            "user_id": 123,
            "access_token": "jwt.token.here"
        })
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/register",
                json={
                    "full_name": "Test User",
                    "email": "test@example.com",
                    "password": "SecurePass123!",
                    "recaptcha_token": "recaptcha_token"
                }
            )
            
            assert response.status_code == 201
            data = response.json()
            assert "access_token" in data
            assert "message" in data
            assert data["user_id"] == 123
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)
    
    @pytest.mark.asyncio
    async def test_register_duplicate_email(self):
        """Test: Registro con email duplicado"""
        from fastapi import HTTPException
        mock_facade = MagicMock()
        mock_facade.register_user = AsyncMock(
            side_effect=HTTPException(status_code=409, detail="Este correo ya está registrado")
        )
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/register",
                json={
                    "full_name": "Test",
                    "email": "duplicate@example.com",
                    "password": "SecurePass123!",
                    "recaptcha_token": "token"
                }
            )
            
            assert response.status_code == 409
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)
    
    @pytest.mark.asyncio
    async def test_register_invalid_recaptcha(self):
        """Test: Registro con reCAPTCHA inválido"""
        from fastapi import HTTPException
        mock_facade = MagicMock()
        mock_facade.register_user = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="reCAPTCHA inválido")
        )
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/register",
                json={
                    "full_name": "Test",
                    "email": "test@example.com",
                    "password": "SecurePass123!",
                    "recaptcha_token": "invalid"
                }
            )
            
            assert response.status_code >= 400
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)


class TestActivateRoute:
    """Tests para POST /auth/activation"""
    
    @pytest.mark.asyncio
    async def test_activate_success(self):
        """Test: Activación exitosa de cuenta"""
        mock_facade = MagicMock()
        mock_facade.activate_account = AsyncMock(
            return_value={"message": "Cuenta activada exitosamente"}
        )
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/activation",
                json={"token": "valid.activation.token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "message" in data
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)
    
    @pytest.mark.asyncio
    async def test_activate_invalid_token(self):
        """Test: Activación con token inválido"""
        from fastapi import HTTPException
        mock_facade = MagicMock()
        mock_facade.activate_account = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="Token inválido o expirado")
        )
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/activation",
                json={"token": "invalid.token"}
            )
            
            assert response.status_code >= 400
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)
    
    @pytest.mark.asyncio
    async def test_activate_malformed_token(self):
        """Test: Activación con token malformado"""
        from fastapi import HTTPException
        mock_facade = MagicMock()
        mock_facade.activate_account = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="formato de token inválido")
        )
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/activation",
                json={"token": "malformed"}
            )
            
            assert response.status_code >= 400
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)


class TestResendActivationRoute:
    """Tests para POST /auth/activation/resend"""
    
    @pytest.mark.asyncio
    async def test_resend_success(self):
        """Test: Reenvío exitoso de correo de activación"""
        mock_facade = MagicMock()
        mock_facade.resend_activation_email = AsyncMock(
            return_value={"message": "Correo reenviado"}
        )
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/activation/resend",
                json={"email": "test@example.com"}
            )
            
            assert response.status_code == 200
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)
    
    @pytest.mark.asyncio
    async def test_resend_no_payment(self):
        """Test: Reenvío bloqueado por falta de pago"""
        from fastapi import HTTPException
        mock_facade = MagicMock()
        mock_facade.resend_activation_email = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="activation_blocked_no_payment")
        )
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/activation/resend",
                json={"email": "test@example.com"}
            )
            
            assert response.status_code >= 400
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)
    
    @pytest.mark.asyncio
    async def test_resend_generic_error(self):
        """Test: Error genérico en reenvío"""
        from fastapi import HTTPException
        mock_facade = MagicMock()
        mock_facade.resend_activation_email = AsyncMock(
            side_effect=HTTPException(status_code=400, detail="Error genérico")
        )
        
        from app.modules.auth.facades import get_auth_facade
        app.dependency_overrides[get_auth_facade] = lambda: mock_facade
        
        try:
            response = client.post(
                "/auth/activation/resend",
                json={"email": "test@example.com"}
            )
            
            assert response.status_code >= 400
        finally:
            app.dependency_overrides.pop(get_auth_facade, None)
