# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/models/__init__.py

Modelos del módulo de perfil de usuario.

Nota: El modelo User se encuentra en app.modules.auth.models
y se reutiliza aquí para operaciones de perfil.

Autor: DoxAI
Fecha: 2025-10-18
"""

from app.modules.auth.models import User

__all__ = ["User"]
