# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/schemas/auth_schemas.py

Schemas Pydantic para operaciones de autenticación en DoxAI.

Incluye:
- Registro de usuario
- Login
- Activación de cuenta
- Recuperación de contraseña
- Respuestas estandarizadas

Autor: Ixchel Beristain
Fecha: 18/10/2025
"""

from typing import Optional, Literal
from datetime import datetime
from pydantic import EmailStr, Field, field_validator

from app.shared.utils import UTF8SafeModel
from app.modules.auth.enums import UserRole, UserStatus


# ========== REQUESTS ==========

class RegisterRequest(UTF8SafeModel):
    """Petición de registro de nuevo usuario"""
    full_name: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    # Teléfono: acepta 10 dígitos (MX) o formato internacional E.164 laxo
    phone: Optional[str] = Field(
        None,
        pattern=r'^(\+?[0-9]{1,4})?[0-9]{7,15}$',
        description="Acepta: 10 dígitos locales o formato internacional (+52 55 1234 5678). Sin espacios ni guiones."
    )
    # Opcional para CLI/tests; se valida en verify_recaptcha_or_raise si RECAPTCHA_ENABLED=true
    recaptcha_token: Optional[str] = Field(None, min_length=1)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        """Normaliza email a minúsculas"""
        return v.lower().strip() if v else v
    
    @field_validator('phone', mode='before')
    @classmethod
    def normalize_phone(cls, v):
        """Normaliza teléfono: elimina espacios, guiones, paréntesis"""
        if v is None or v == "":
            return None
        # Remover caracteres de formato comunes
        cleaned = ''.join(c for c in str(v) if c.isdigit() or c == '+')
        return cleaned if cleaned else None


class LoginRequest(UTF8SafeModel):
    """Petición de inicio de sesión"""
    email: EmailStr
    password: str = Field(..., min_length=1)
    # Opcional para CLI/tests; se valida si RECAPTCHA_ENABLED=true
    recaptcha_token: Optional[str] = Field(None, min_length=1)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        """Normaliza email a minúsculas"""
        return v.lower().strip() if v else v


class ActivationRequest(UTF8SafeModel):
    """Petición de activación de cuenta - sin validación estricta, el servicio valida"""
    token: str = ""  # Sin min_length - toda validación va en el servicio


class ResendActivationRequest(UTF8SafeModel):
    """Petición de reenvío de email de activación"""
    email: EmailStr

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        """Normaliza email a minúsculas"""
        return v.lower().strip() if v else v


class PasswordResetRequest(UTF8SafeModel):
    """Petición de recuperación de contraseña"""
    email: EmailStr
    # Opcional para CLI/tests; se valida si RECAPTCHA_ENABLED=true
    recaptcha_token: Optional[str] = Field(None, min_length=1)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        """Normaliza email a minúsculas"""
        return v.lower().strip() if v else v


class PasswordResetConfirmRequest(UTF8SafeModel):
    """Confirmación de nueva contraseña"""
    token: str = Field(..., min_length=10)
    new_password: str = Field(
        ..., min_length=8, max_length=128,
        description="Mín. 8 caracteres; sugiere combinar mayúsculas, minúsculas y dígitos"
    )


# ========== RESPONSES ==========

class UserOut(UTF8SafeModel):
    """Información pública del usuario"""
    user_id: int
    user_email: EmailStr
    user_full_name: str
    user_role: UserRole
    user_status: UserStatus
    user_phone: Optional[str] = None
    user_is_activated: bool = False
    user_created_at: Optional[datetime] = None


class RegisterResponse(UTF8SafeModel):
    """Respuesta de registro exitoso"""
    message: str
    user_id: int
    access_token: str
    activation_email_sent: bool = True  # False cuando falla envío (MailerSend trial limit, etc.)


class LoginResponse(UTF8SafeModel):
    """Respuesta de login exitoso"""
    message: str
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


class MessageResponse(UTF8SafeModel):
    """Respuesta genérica con mensaje"""
    message: str
    code: Optional[str] = None
    credits_assigned: Optional[int] = None


class TokenResponse(UTF8SafeModel):
    """Respuesta con token de acceso"""
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshRequest(UTF8SafeModel):
    refresh_token: str


class CheckEmailRequest(UTF8SafeModel):
    """Petición para verificar disponibilidad de email"""
    email: EmailStr
    
    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        return v.lower().strip() if v else v


class CheckEmailResponse(UTF8SafeModel):
    """Respuesta de verificación de email"""
    available: bool
    message: Optional[str] = None

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
]
