
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/__init__.py

Auth package public API:

Expone:
- enums
- schemas
- facades
- dependencies (get_current_user_id)
- get_auth_routers()  ← IMPORTANTE para que app.main pueda montar rutas
"""

from .enums import *            # noqa: F401,F403
from .schemas import *          # noqa: F401,F403
from .facades import *          # noqa: F401,F403

# 🔐 Dependencias de autenticación
from .dependencies import get_current_user_id, validate_jwt_token

# 🚀 Importamos los routers para exponerlos fuera del paquete
from .routes import get_auth_routers

__all__ = [
    "get_auth_routers",
    "get_current_user_id",
    "validate_jwt_token",
]
# Fin del archivo backend/app/modules/auth/__init__.py