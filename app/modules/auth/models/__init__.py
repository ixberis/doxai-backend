# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/__init__.py

Modelos ORM del módulo de autenticación.

IMPORTANTE: El orden de imports es crítico. Los modelos hijos (que tienen FK)
deben importarse ANTES que AppUser para que SQLAlchemy pueda resolver
las relationships correctamente.

Autor: Ixchel Beristáin
Fecha: 18/10/2025
"""

# 1. Primero importar los modelos hijos (tienen FKs hacia app_users)
from .activation_models import AccountActivation
from .password_reset_models import PasswordReset
from .login_models import LoginAttempt, UserSession

# 2. Luego importar AppUser (tiene relationships hacia los hijos)
from .user_models import User, AppUser

__all__ = [
    "User",
    "AppUser",
    "AccountActivation",
    "PasswordReset",
    "LoginAttempt",
    "UserSession",
]
