# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/schemas/profile_schemas.py

Schemas Pydantic para operaciones del perfil de usuario en DoxAI.

Incluye:
- Consulta del perfil de usuario
- Actualización de datos personales (nombre, teléfono)
- Estado de suscripción

Autor: DoxAI
Fecha: 2025-10-18
"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import Field, EmailStr, ConfigDict

from app.shared.utils.base_models import UTF8SafeModel
from app.modules.auth.enums import UserRole, UserStatus

# Alias para mayor claridad semántica en el contexto de suscripciones
SubscriptionStatus = UserStatus


# ========== REQUEST SCHEMAS ==========

class UserProfileUpdateRequest(UTF8SafeModel):
    """
    Request para actualizar perfil de usuario.
    
    Permite actualizar:
    - Nombre completo (3-100 caracteres)
    - Teléfono (formato internacional)
    """
    user_full_name: Optional[str] = Field(
        None,
        min_length=3,
        max_length=100,
        description="Nombre completo del usuario"
    )
    user_phone: Optional[str] = Field(
        None,
        pattern=r'^\+?[0-9\s\-()]{7,20}$',
        description="Teléfono en formato internacional"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_full_name": "Juan Pérez García",
                "user_phone": "+52 55 1234 5678"
            }
        }
    )


# ========== RESPONSE SCHEMAS ==========

class UserProfileResponse(UTF8SafeModel):
    """
    Response con información completa del perfil de usuario.
    
    Incluye datos personales y estado de cuenta/suscripción.
    """
    user_id: UUID = Field(..., description="ID único del usuario")
    user_email: EmailStr = Field(..., description="Email del usuario")
    user_full_name: str = Field(..., description="Nombre completo")
    user_phone: Optional[str] = Field(None, description="Teléfono")
    user_role: UserRole = Field(..., description="Rol del usuario")
    user_status: UserStatus = Field(..., description="Estado de la cuenta")
    user_subscription_status: SubscriptionStatus = Field(
        ...,
        description="Estado de suscripción"
    )
    subscription_period_end: Optional[datetime] = Field(
        None,
        description="Fecha de fin de suscripción"
    )
    user_created_at: datetime = Field(..., description="Fecha de registro")
    user_updated_at: datetime = Field(..., description="Última actualización")
    user_last_login: Optional[datetime] = Field(None, description="Último login")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_email": "user@example.com",
                "user_full_name": "Juan Pérez",
                "user_phone": "+52 55 1234 5678",
                "user_role": "customer",
                "subscription_status": "free"
            }
        }
    )


class UserProfileUpdateResponse(UTF8SafeModel):
    """Response tras actualización exitosa del perfil"""
    success: bool = Field(True, description="Indica si la operación fue exitosa")
    message: str = Field(..., description="Mensaje descriptivo")
    updated_at: datetime = Field(..., description="Timestamp de actualización")
    user: UserProfileResponse = Field(..., description="Perfil actualizado")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Perfil actualizado correctamente",
                "updated_at": "2025-10-18T15:30:00Z",
                "user": {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "user_email": "user@example.com",
                    "user_full_name": "Juan Pérez",
                    "user_phone": "+52 55 1234 5678"
                }
            }
        }
    )


class SubscriptionStatusResponse(UTF8SafeModel):
    """Response con el estado de suscripción del usuario"""
    user_id: UUID = Field(..., description="ID del usuario")
    user_email: EmailStr = Field(..., description="Email del usuario")
    subscription_status: SubscriptionStatus = Field(
        ...,
        description="Estado actual de la suscripción"
    )
    subscription_period_start: Optional[datetime] = Field(
        None,
        description="Inicio del periodo actual"
    )
    subscription_period_end: Optional[datetime] = Field(
        None,
        description="Fin del periodo actual"
    )
    last_payment_date: Optional[datetime] = Field(
        None,
        description="Fecha del último pago"
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_email": "user@example.com",
                "subscription_status": "active",
                "subscription_period_start": "2025-10-01T00:00:00Z",
                "subscription_period_end": "2025-11-01T00:00:00Z",
                "last_payment_date": "2025-10-15T10:30:00Z"
            }
        }
    )
