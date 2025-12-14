# -*- coding: utf-8 -*-
"""
tests/modules/auth/services/test_audit_service.py

Tests unitarios para AuditService.

Autor: DoxAI
Fecha: 02/11/2025
"""

import pytest
import json
import logging

from app.modules.auth.services.audit_service import AuditService, AuditEventType


class TestAuditService:
    """Tests para servicio de auditoría"""
    
    def test_obfuscate_email(self):
        """Verifica ofuscación correcta de emails"""
        # Email normal
        assert AuditService._obfuscate_email("usuario@example.com") == "usu***@example.com"
        
        # Email corto
        assert AuditService._obfuscate_email("ab@example.com") == "a***@example.com"
        
        # Email muy corto
        assert AuditService._obfuscate_email("a@example.com") == "a***@example.com"
        
        # Email inválido
        assert AuditService._obfuscate_email("invalid") == "***"
        assert AuditService._obfuscate_email("") == "***"
    
    def test_log_event_structure(self, caplog):
        """Verifica estructura del log de auditoría"""
        with caplog.at_level(logging.INFO):
            AuditService.log_event(
                event_type=AuditEventType.LOGIN_SUCCESS,
                user_id="user123",
                email="test@example.com",
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
                success=True,
            )
        
        # Verificar que se generó un log
        assert len(caplog.records) == 1
        
        # Parsear el JSON del log
        log_entry = json.loads(caplog.records[0].message)
        
        # Verificar campos requeridos
        assert log_entry["event_type"] == "login_success"
        assert log_entry["success"] is True
        assert log_entry["user_id"] == "user123"
        assert log_entry["email"] == "tes***@example.com"  # ofuscado
        assert log_entry["ip_address"] == "192.168.1.1"
        assert "timestamp" in log_entry
    
    def test_log_event_with_error(self, caplog):
        """Verifica log de eventos con error"""
        with caplog.at_level(logging.WARNING):
            AuditService.log_event(
                event_type=AuditEventType.LOGIN_FAILED,
                email="test@example.com",
                ip_address="192.168.1.1",
                success=False,
                error_message="Credenciales inválidas",
            )
        
        # Verificar nivel WARNING para fallos
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        
        # Verificar contenido
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["success"] is False
        assert log_entry["error"] == "Credenciales inválidas"
    
    def test_log_login_success_helper(self, caplog):
        """Verifica helper log_login_success"""
        with caplog.at_level(logging.INFO):
            AuditService.log_login_success(
                user_id="user123",
                email="test@example.com",
                ip_address="192.168.1.1",
                user_agent="Chrome",
            )
        
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["event_type"] == "login_success"
        assert log_entry["user_id"] == "user123"
    
    def test_log_login_failed_helper(self, caplog):
        """Verifica helper log_login_failed"""
        with caplog.at_level(logging.WARNING):
            AuditService.log_login_failed(
                email="test@example.com",
                ip_address="192.168.1.1",
                reason="Contraseña incorrecta",
            )
        
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["event_type"] == "login_failed"
        assert log_entry["error"] == "Contraseña incorrecta"
        assert log_entry["success"] is False
    
    def test_log_login_blocked_helper(self, caplog):
        """Verifica helper log_login_blocked"""
        with caplog.at_level(logging.WARNING):
            AuditService.log_login_blocked(
                email="test@example.com",
                ip_address="192.168.1.1",
            )
        
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["event_type"] == "login_blocked"
        assert "Rate limit" in log_entry["error"]
    
    def test_log_register_success_helper(self, caplog):
        """Verifica helper log_register_success"""
        with caplog.at_level(logging.INFO):
            AuditService.log_register_success(
                user_id="user123",
                email="test@example.com",
                ip_address="192.168.1.1",
            )
        
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["event_type"] == "register_success"
    
    def test_log_activation_success_helper(self, caplog):
        """Verifica helper log_activation_success"""
        with caplog.at_level(logging.INFO):
            AuditService.log_activation_success(
                user_id="user123",
                email="test@example.com",
            )
        
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["event_type"] == "activation_success"
    
    def test_log_password_reset_request_helper(self, caplog):
        """Verifica helper log_password_reset_request"""
        with caplog.at_level(logging.INFO):
            AuditService.log_password_reset_request(
                email="test@example.com",
                ip_address="192.168.1.1",
            )
        
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["event_type"] == "password_reset_request"
    
    def test_log_password_reset_confirm_helper(self, caplog):
        """Verifica helper log_password_reset_confirm"""
        with caplog.at_level(logging.INFO):
            AuditService.log_password_reset_confirm(
                user_id="user123",
                email="test@example.com",
            )
        
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["event_type"] == "password_reset_confirm"
    
    def test_log_refresh_token_success_helper(self, caplog):
        """Verifica helper log_refresh_token_success"""
        with caplog.at_level(logging.INFO):
            AuditService.log_refresh_token_success(user_id="user123")
        
        log_entry = json.loads(caplog.records[0].message)
        assert log_entry["event_type"] == "refresh_token_success"
    
    def test_log_extra_data(self, caplog):
        """Verifica inclusión de datos extra en logs"""
        with caplog.at_level(logging.INFO):
            AuditService.log_event(
                event_type=AuditEventType.LOGIN_SUCCESS,
                user_id="user123",
                extra_data={"source": "mobile_app", "version": "1.2.3"},
            )
        
        log_entry = json.loads(caplog.records[0].message)
        assert "extra" in log_entry
        assert log_entry["extra"]["source"] == "mobile_app"
        assert log_entry["extra"]["version"] == "1.2.3"


# Fin del archivo
