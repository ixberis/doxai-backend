
from __future__ import annotations
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/schemas/user_schemas.py

Esquemas Pydantic relacionados con usuarios en la aplicación DoxAI.

Incluye:
- Actualización de información personal del usuario
- Cambio de estado (activo, suspendido, cancelado)
- Cambio de rol
- Vista administrativa del usuario

`UserAdminView` hereda de `UserOut` para evitar duplicar campos y
mantener una única fuente de verdad.

Autor: Ixchel Beristain
Fecha: 19/10/2025
"""

from typing import Optional
from pydantic import Field

from app.modules.auth.enums import UserStatus, UserRole
from app.shared.utils import UTF8SafeModel
from .auth_schemas import UserOut


# ========== PETICIONES ==========

class UpdateUserProfileRequest(UTF8SafeModel):
    user_full_name: Optional[str] = Field(None, min_length=3, max_length=100)
    user_phone: Optional[str] = Field(
        None,
        pattern=r'^\+?[0-9\s\-()]{7,20}$',
        description="E.164 laxo: admite +, espacios, guiones y paréntesis (7–20 dígitos)"
    )


class ChangeUserStatusRequest(UTF8SafeModel):
    user_status: UserStatus


class ChangeUserRoleRequest(UTF8SafeModel):
    user_role: UserRole


# ========== RESPUESTAS ==========

class UserAdminView(UserOut):
    """Vista de usuario para panel administrativo.

    Por ahora hereda 1:1 de UserOut. Si en el futuro se requieren campos
    exclusivos de administración (e.g., flags internos, métricas),
    agrégalos aquí.
    """
    pass


__all__ = [
    "UpdateUserProfileRequest",
    "ChangeUserStatusRequest",
    "ChangeUserRoleRequest",
    "UserAdminView",
]
# Fin del archivo
