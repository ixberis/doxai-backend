# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/models/__init__.py

Modelos ORM del módulo de autenticación.

Autor: Ixchel Beristáin
Fecha: 18/10/2025
"""

from .user_models import User, AppUser
from .activation_models import AccountActivation
from .password_reset_models import PasswordReset
from .login_models import LoginAttempt, UserSession

__all__ = [
    "User",
    "AppUser",  # Nombre real del modelo
    "AccountActivation",
    "PasswordReset",
    "LoginAttempt",
    "UserSession",
]
