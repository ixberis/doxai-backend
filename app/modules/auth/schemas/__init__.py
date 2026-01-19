# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/schemas/__init__.py

Schemas Pydantic del módulo de autenticación.

Autor: Ixchel Beristáin
Fecha: 18/10/2025
"""

from .auth_schemas import (
    # Requests
    RegisterRequest,
    LoginRequest,
    ActivationRequest,
    ResendActivationRequest,
    PasswordResetRequest,
    PasswordResetConfirmRequest,
    RefreshRequest,
    CheckEmailRequest,
    
    # Responses
    UserOut,
    RegisterResponse,
    LoginResponse,
    MessageResponse,
    TokenResponse,
    CheckEmailResponse,
)

from .session_schemas import (
    # Outputs de auditoría
    LoginAttemptOut,
    SessionOut,
    
    # Filtros
    LoginAttemptsFilterRequest,
    SessionsFilterRequest,
    
    # Respuestas paginadas
    PaginationMeta,
    LoginAttemptsPaginatedResponse,
    SessionsPaginatedResponse,
    
    # Respuestas de operaciones
    RevokeSessionResponse,
    RevokeAllSessionsResponse,
)

from .user_schemas import UserOut, UserAdminView
from .user_dto import UserDTO
from .login_user_dto import LoginUserDTO, LoginUserDTOMappingError
from .auth_context_dto import AuthContextDTO, AuthContextDTOMappingError

__all__ = [
    # Requests
    "RegisterRequest",
    "LoginRequest",
    "ActivationRequest",
    "ResendActivationRequest",
    "PasswordResetRequest",
    "PasswordResetConfirmRequest",
    "RefreshRequest",
    "CheckEmailRequest",
    
    # Responses
    "UserOut",
    "RegisterResponse",
    "LoginResponse",
    "MessageResponse",
    "TokenResponse",
    "CheckEmailResponse",
    
    # Session/Auditoría
    "LoginAttemptOut",
    "SessionOut",
    "LoginAttemptsFilterRequest",
    "SessionsFilterRequest",
    "PaginationMeta",
    "LoginAttemptsPaginatedResponse",
    "SessionsPaginatedResponse",
    "RevokeSessionResponse",
    "RevokeAllSessionsResponse",

    "UserOut",
    "UserAdminView",
    
    # DTOs (Core mode)
    "UserDTO",
    "LoginUserDTO",
    "LoginUserDTOMappingError",
    "AuthContextDTO",
    "AuthContextDTOMappingError",
]
