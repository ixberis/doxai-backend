
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/facades/__init__.py

Punto de entrada de facades del módulo Auth.

Exporta:
    - AuthFacade
    - get_auth_facade

Estos objetos son usados por las rutas (auth_public, auth_tokens, auth_admin)
para orquestar los flujos de autenticación apoyándose en AuthService.

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from .auth_facade import AuthFacade, get_auth_facade

__all__ = [
    "AuthFacade",
    "get_auth_facade",
]

# Fin del script backend/app/modules/auth/facades/__init__.py

