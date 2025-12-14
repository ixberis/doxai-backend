# -*- coding: utf-8 -*-
"""
tests/modules/auth/services/test_login_attempt_service.py

Tests unitarios para LoginAttemptService.

Autor: DoxAI
Fecha: 02/11/2025
"""

import pytest
import os
from datetime import timedelta
from fastapi import HTTPException

from app.modules.auth.services.login_attempt_service import LoginAttemptService
from app.shared.config.config_loader import get_settings

class TestLoginAttemptService:
    """Tests para rate limiting de intentos de login"""
    
    def test_initialization(self, monkeypatch):
        """Verifica inicialización correcta del servicio"""
        # Establecer explícitamente los valores esperados
        monkeypatch.setenv('LOGIN_ATTEMPTS_LIMIT', '5')
        monkeypatch.setenv('LOGIN_ATTEMPTS_TIME_WINDOW_MINUTES', '15')
        monkeypatch.setenv('LOGIN_LOCKOUT_DURATION_MINUTES', '30')
        
        # Limpiar caché de settings para asegurar que use valores actualizados
        get_settings.cache_clear()
        
        service = LoginAttemptService()
        assert service.max_attempts == 5
        assert service.time_window_minutes == 15
        assert service.lockout_duration_minutes == 30
    
    def test_check_rate_limit_allows_initial_attempts(self):
        """Verifica que los primeros intentos sean permitidos"""
        service = LoginAttemptService()
        
        # No debe lanzar excepción en los primeros intentos
        service.check_rate_limit("192.168.1.1", "ip")
        service.check_rate_limit("test@example.com", "email")
    
    def test_record_failed_attempt_increments_counter(self):
        """Verifica que se incrementen los contadores tras intentos fallidos"""
        service = LoginAttemptService()
        ip = "192.168.1.1"
        email = "test@example.com"
        
        # Registrar varios intentos fallidos
        for _ in range(3):
            service.record_failed_attempt(ip, email)
        
        # Verificar que se decrementó el contador de intentos restantes
        remaining_ip = service.remaining_attempts(ip, "ip")
        remaining_email = service.remaining_attempts(email, "email")
        
        assert remaining_ip == 2  # 5 max - 3 intentos
        assert remaining_email == 2
    
    def test_lockout_after_max_attempts(self):
        """Verifica que se bloquee tras exceder el límite"""
        service = LoginAttemptService()
        ip = "192.168.1.1"
        email = "test@example.com"
        
        # Exceder el límite de intentos
        for _ in range(service.max_attempts):
            service.record_failed_attempt(ip, email)
        
        # Siguiente verificación debe lanzar 429
        with pytest.raises(HTTPException) as exc_info:
            service.check_rate_limit(ip, "ip")
        
        assert exc_info.value.status_code == 429
        assert "Demasiados intentos" in exc_info.value.detail
    
    def test_successful_login_clears_counters(self):
        """Verifica que login exitoso limpie los contadores"""
        service = LoginAttemptService()
        ip = "192.168.1.1"
        email = "test@example.com"
        
        # Registrar algunos intentos fallidos
        service.record_failed_attempt(ip, email)
        service.record_failed_attempt(ip, email)
        
        # Login exitoso debe limpiar
        service.record_successful_login(ip, email)
        
        # Verificar que se resetearon los contadores
        remaining_ip = service.remaining_attempts(ip, "ip")
        remaining_email = service.remaining_attempts(email, "email")
        
        assert remaining_ip == service.max_attempts
        assert remaining_email == service.max_attempts
    
    def test_separate_tracking_ip_and_email(self):
        """Verifica que IP y email se tracken independientemente"""
        service = LoginAttemptService()
        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"
        email = "test@example.com"
        
        # Fallar desde IP1
        for _ in range(3):
            service.record_failed_attempt(ip1, email)
        
        # IP2 debe tener límite completo
        remaining_ip2 = service.remaining_attempts(ip2, "ip")
        assert remaining_ip2 == service.max_attempts
        
        # Email debe tener 3 intentos consumidos
        remaining_email = service.remaining_attempts(email, "email")
        assert remaining_email == 2
    
    def test_get_remaining_attempts_when_locked(self):
        """Verifica que devuelva 0 intentos restantes cuando está bloqueado"""
        service = LoginAttemptService()
        ip = "192.168.1.1"
        
        # Bloquear
        for _ in range(service.max_attempts):
            service.record_failed_attempt(ip, "test@example.com")
        
        # Debe devolver 0
        remaining = service.remaining_attempts(ip, "ip")
        assert remaining == 0


# Fin del archivo
