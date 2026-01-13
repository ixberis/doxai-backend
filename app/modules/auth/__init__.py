# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/__init__.py

Auth package public API:

Expone:
- enums
- schemas
- facades
- dependencies (require_admin, require_admin_strict)
- token_service (get_current_user_id, get_current_user_ctx)
- get_auth_routers()  ← IMPORTANTE para que app.main pueda montar rutas

NOTA: get_current_user_id y get_current_user_ctx están en token_service,
      NO en dependencies (que solo contiene helpers de rol).
"""

from .enums import *            # noqa: F401,F403
from .schemas import *          # noqa: F401,F403
from .facades import *          # noqa: F401,F403

# 🔐 Dependencias de autenticación (rol)
from .dependencies import require_admin, require_admin_strict

# 🔐 Funciones de autenticación (token)
from .services.token_service import get_current_user_id, get_current_user_ctx

# 🚀 Importamos los routers para exponerlos fuera del paquete
from .routes import get_auth_routers

__all__ = [
    "get_auth_routers",
    "get_current_user_id",
    "get_current_user_ctx",
    "require_admin",
    "require_admin_strict",
]
# Fin del archivo backend/app/modules/auth/__init__.py