# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/__init__.py

Exportación de utilidades comunes consolidadas.

Autor: DoxAI
Fecha: 2025-10-18 (Consolidación modular)
"""

from .base_models import UTF8SafeModel, EmailStr, Field
from .http_exceptions import (
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    UnprocessableEntityException,
    InternalServerException,
)
from .security import (
    hash_password,
    verify_password,
    create_access_token,
    create_activation_token,
    decode_token,
    verify_token_type,
)
from .validators import (
    validate_email,
    validate_phone,
    validate_password_strength,
    validate_uuid,
    sanitize_string,
)

__all__ = [
    # Base models
    "UTF8SafeModel",
    "EmailStr",
    "Field",
    
    # HTTP Exceptions
    "BadRequestException",
    "UnauthorizedException",
    "ForbiddenException",
    "NotFoundException",
    "ConflictException",
    "UnprocessableEntityException",
    "InternalServerException",
    
    # Security
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_activation_token",
    "decode_token",
    "verify_token_type",
    
    # Validators
    "validate_email",
    "validate_phone",
    "validate_password_strength",
    "validate_uuid",
    "sanitize_string",
]
