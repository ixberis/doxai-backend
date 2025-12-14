
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/repositories/__init__.py

Punto de ensamblado de los repositorios del módulo Auth.
Centraliza las exportaciones públicas para facilitar los imports desde
otros módulos (facades, servicios, pruebas).

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from .user_repository import UserRepository
from .activation_repository import ActivationRepository
from .login_attempt_repository import LoginAttemptRepository
from .password_reset_repository import PasswordResetRepository
from .token_repository import TokenRepository

__all__ = [
    "UserRepository",
    "ActivationRepository",
    "LoginAttemptRepository",
    "PasswordResetRepository",
    "TokenRepository",
]

# Fin del archivo backend/app/modules/auth/repositories/__init__.py
