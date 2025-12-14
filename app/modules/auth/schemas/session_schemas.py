# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/schemas/session_schemas.py

Schemas Pydantic para sesiones y auditoría de login en DoxAI.

Incluye:
- Representación de intentos de login (LoginAttemptOut)
- Representación de sesiones activas (SessionOut)
- Filtros de paginación para consultas administrativas
- Respuestas paginadas para listados de auditoría

Autor: Ixchel Beristain
Fecha: 25/10/2025
"""

from typing import Optional, List
from datetime import datetime, timezone
from pydantic import Field, field_validator

from app.shared.utils import UTF8SafeModel
from app.modules.auth.enums import LoginFailureReason, TokenType


# ========== RESPONSES DE AUDITORÍA ==========

class LoginAttemptOut(UTF8SafeModel):
    """Representación de un intento de login para auditoría"""
    attempt_id: int
    user_id: int
    success: bool
    reason: Optional[LoginFailureReason] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime


class SessionOut(UTF8SafeModel):
    """Representación de una sesión de usuario"""
    session_id: int
    user_id: int
    token_type: TokenType
    issued_at: datetime
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    is_active: bool = True
    
    @field_validator('is_active', mode='before')
    @classmethod
    def compute_is_active(cls, v, info):
        """Calcula si la sesión está activa basándose en revoked_at y expires_at"""
        # Si viene el valor directamente, usarlo
        if isinstance(v, bool):
            return v
        
        # Calcular basándose en los otros campos si están disponibles
        data = info.data
        if data.get('revoked_at') is not None:
            return False
        
        expires_at = data.get('expires_at')
        if expires_at and isinstance(expires_at, datetime):
            now = datetime.now(timezone.utc)
            # Normaliza ambas fechas a aware-UTC para evitar errores de comparación
            exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
            return exp > now
        
        return True


# ========== FILTROS DE PAGINACIÓN ==========

class LoginAttemptsFilterRequest(UTF8SafeModel):
    """Filtros para consultar intentos de login (admin)"""
    user_id: Optional[int] = None
    success: Optional[bool] = None
    reason: Optional[LoginFailureReason] = None
    ip_address: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    
    # Paginación
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
    
    @field_validator('page_size')
    @classmethod
    def validate_page_size(cls, v):
        """Limita el tamaño de página a valores razonables"""
        if v > 500:
            return 500
        return v


class SessionsFilterRequest(UTF8SafeModel):
    """Filtros para consultar sesiones (admin)"""
    user_id: Optional[int] = None
    token_type: Optional[TokenType] = None
    is_active: Optional[bool] = None
    issued_from: Optional[datetime] = None
    issued_to: Optional[datetime] = None
    
    # Paginación
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)
    
    @field_validator('page_size')
    @classmethod
    def validate_page_size(cls, v):
        """Limita el tamaño de página a valores razonables"""
        if v > 500:
            return 500
        return v


# ========== RESPUESTAS PAGINADAS ==========

class PaginationMeta(UTF8SafeModel):
    """Metadata de paginación"""
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class LoginAttemptsPaginatedResponse(UTF8SafeModel):
    """Respuesta paginada de intentos de login"""
    items: List[LoginAttemptOut]
    meta: PaginationMeta


class SessionsPaginatedResponse(UTF8SafeModel):
    """Respuesta paginada de sesiones"""
    items: List[SessionOut]
    meta: PaginationMeta


# ========== RESPUESTAS DE OPERACIONES ==========

class RevokeSessionResponse(UTF8SafeModel):
    """Respuesta de revocación de sesión"""
    message: str
    session_id: int
    revoked_at: datetime


class RevokeAllSessionsResponse(UTF8SafeModel):
    """Respuesta de revocación masiva de sesiones"""
    message: str
    user_id: int
    sessions_revoked: int
    revoked_at: datetime


__all__ = [
    # Outputs de auditoría
    "LoginAttemptOut",
    "SessionOut",
    
    # Filtros
    "LoginAttemptsFilterRequest",
    "SessionsFilterRequest",
    
    # Respuestas paginadas
    "PaginationMeta",
    "LoginAttemptsPaginatedResponse",
    "SessionsPaginatedResponse",
    
    # Respuestas de operaciones
    "RevokeSessionResponse",
    "RevokeAllSessionsResponse",
]
# Fin del archivo session_schemas.py
