
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/audit_service.py

Servicio de auditoría para eventos de autenticación.
Registra eventos importantes con logging estructurado JSON.

Autor: DoxAI
Fecha: 02/11/2025
"""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Tipos de eventos auditables"""
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGIN_BLOCKED = "login_blocked"
    REGISTER_SUCCESS = "register_success"
    REGISTER_FAILED = "register_failed"
    ACTIVATION_SUCCESS = "activation_success"
    ACTIVATION_FAILED = "activation_failed"
    ACTIVATION_RESEND = "activation_resend"
    PASSWORD_RESET_REQUEST = "password_reset_request"
    PASSWORD_RESET_CONFIRM = "password_reset_confirm"
    PASSWORD_RESET_FAILED = "password_reset_failed"
    REFRESH_TOKEN_SUCCESS = "refresh_token_success"
    REFRESH_TOKEN_FAILED = "refresh_token_failed"
    LOGOUT = "logout"


class AuditService:
    """
    Servicio de auditoría para eventos de autenticación.
    
    Registra eventos con logging estructurado JSON para facilitar:
    - Análisis de seguridad
    - Detección de anomalías
    - Cumplimiento regulatorio
    - Debugging de problemas de autenticación
    """
    
    @staticmethod
    def log_event(
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Registra un evento de auditoría con logging estructurado.
        
        Args:
            event_type: Tipo de evento (enum AuditEventType)
            user_id: ID del usuario (si aplica)
            email: Email del usuario (ofuscado en logs)
            ip_address: Dirección IP del cliente
            user_agent: User agent del navegador
            success: Si el evento fue exitoso
            error_message: Mensaje de error (si aplica)
            extra_data: Datos adicionales contextuales
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Ofuscar email para logs (mostrar solo primeros 3 chars + dominio)
        email_safe = AuditService._obfuscate_email(email) if email else None
        
        # Construir payload de auditoría
        audit_payload = {
            "timestamp": timestamp,
            "event_type": event_type.value,
            "success": success,
            "user_id": user_id,
            "email": email_safe,
            "ip_address": ip_address,
            "user_agent": user_agent[:100] if user_agent else None,  # Truncar UA
        }
        
        if error_message:
            audit_payload["error"] = error_message
        
        if extra_data:
            audit_payload["extra"] = extra_data
        
        # Log estructurado JSON
        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            json.dumps(audit_payload, ensure_ascii=False, default=str)
        )
    
    @staticmethod
    def _obfuscate_email(email: str) -> str:
        """
        Ofusca email para logging seguro.
        Ejemplo: usuario@example.com -> usu***@example.com
        """
        if not email or "@" not in email:
            return "***"
        
        local, domain = email.split("@", 1)
        if len(local) <= 3:
            return f"{local[0]}***@{domain}"
        return f"{local[:3]}***@{domain}"
    
    # -------------------- Login -------------------- #
    
    @classmethod
    def log_login_success(
        cls,
        user_id: str,
        email: str,
        ip_address: str,
        user_agent: Optional[str] = None,
    ) -> None:
        """Registra login exitoso"""
        cls.log_event(
            AuditEventType.LOGIN_SUCCESS,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
        )
    
    @classmethod
    def log_login_failed(
        cls,
        email: str,
        ip_address: str,
        reason: str,
        user_agent: Optional[str] = None,
    ) -> None:
        """Registra login fallido"""
        cls.log_event(
            AuditEventType.LOGIN_FAILED,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
            error_message=reason,
        )
    
    @classmethod
    def log_login_blocked(
        cls,
        email: str,
        ip_address: str,
        reason: str = "Rate limit exceeded",
    ) -> None:
        """Registra intento de login bloqueado por rate limiting"""
        cls.log_event(
            AuditEventType.LOGIN_BLOCKED,
            email=email,
            ip_address=ip_address,
            success=False,
            error_message=reason,
        )
    
    # -------------------- Registro -------------------- #
    
    @classmethod
    def log_register_success(
        cls,
        user_id: str,
        email: str,
        ip_address: str,
        user_agent: Optional[str] = None,
    ) -> None:
        """Registra registro exitoso"""
        cls.log_event(
            AuditEventType.REGISTER_SUCCESS,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
        )
    
    @classmethod
    def log_register_failed(
        cls,
        email: str,
        ip_address: Optional[str] = None,
        error_message: Optional[str] = None,
        user_agent: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra fallo durante el registro de usuario"""
        cls.log_event(
            AuditEventType.REGISTER_FAILED,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
            error_message=error_message,
            extra_data=extra_data,
        )
    
    # -------------------- Activación -------------------- #
    
    @classmethod
    def log_activation_success(
        cls,
        user_id: str,
        email: str,
    ) -> None:
        """Registra activación de cuenta exitosa"""
        cls.log_event(
            AuditEventType.ACTIVATION_SUCCESS,
            user_id=user_id,
            email=email,
            success=True,
        )
    
    @classmethod
    def log_activation_resend(
        cls,
        user_id: str,
        email: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Registra reenvío de correo de activación"""
        cls.log_event(
            AuditEventType.ACTIVATION_RESEND,
            user_id=user_id,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
        )
    
    # -------------------- Password reset -------------------- #
    
    @classmethod
    def log_password_reset_request(
        cls,
        email: str,
        ip_address: str,
    ) -> None:
        """Registra solicitud de reset de contraseña"""
        cls.log_event(
            AuditEventType.PASSWORD_RESET_REQUEST,
            email=email,
            ip_address=ip_address,
            success=True,
        )
    
    @classmethod
    def log_password_reset_confirm(
        cls,
        user_id: str,
        email: str,
    ) -> None:
        """Registra confirmación exitosa de reset de contraseña"""
        cls.log_event(
            AuditEventType.PASSWORD_RESET_CONFIRM,
            user_id=user_id,
            email=email,
            success=True,
        )
    
    # -------------------- Refresh token -------------------- #
    
    @classmethod
    def log_refresh_token_success(
        cls,
        user_id: str,
    ) -> None:
        """Registra refresh de token exitoso"""
        cls.log_event(
            AuditEventType.REFRESH_TOKEN_SUCCESS,
            user_id=user_id,
            success=True,
        )

    # -------------------- Logout -------------------- #

    @classmethod
    def log_logout(
        cls,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Registra un logout exitoso."""
        cls.log_event(
            AuditEventType.LOGOUT,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True,
        )



__all__ = ["AuditService", "AuditEventType"]

# Fin del archivo backend/app/modules/auth/services/audit_service.py
