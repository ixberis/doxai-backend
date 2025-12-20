
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/security.py

Módulo de seguridad para Auth en DoxAI:
- Esquema OAuth2 (Bearer)
- Creación / decodificación de JWT
- Hash / verificación de contraseñas
- Config vía settings o variables de entorno (fallbacks seguros)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union

from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt  # pip install "python-jose[cryptography]"

# -----------------------------------------------------------------------------
# Configuración (intenta leer de settings; si no, usa variables de entorno)
# -----------------------------------------------------------------------------
def _load_config() -> tuple[str, str, int]:
    # Intenta importar settings centralizado (ajusta la ruta si tu proyecto difiere)
    # Debe exponer al menos: SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
    try:
        from app.shared.config import settings  # type: ignore
        secret_key = getattr(settings, "SECRET_KEY")
        algorithm = getattr(settings, "JWT_ALGORITHM", "HS256")
        expire_minutes = int(getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 60))
        return secret_key, algorithm, expire_minutes
    except Exception:
        # Fallback a variables de entorno
        secret_key = os.getenv("JWT_SECRET_KEY", "PLEASE_CHANGE_ME_DEV_ONLY")
        algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
        return secret_key, algorithm, expire_minutes


SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES = _load_config()

# -----------------------------------------------------------------------------
# Esquema OAuth2 para extraer el token de Authorization: Bearer <token>
# Ajusta el tokenUrl a tu endpoint real de login si es diferente.
# -----------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# -----------------------------------------------------------------------------
# Hash de contraseñas (delegado a shared/utils/security.py - fuente única)
# -----------------------------------------------------------------------------
from app.shared.utils.security import (
    hash_password as _shared_hash,
    verify_password as _shared_verify,
)

# Re-export para compatibilidad con código existente que importa desde aquí
get_password_hash = _shared_hash
verify_password = _shared_verify


# -----------------------------------------------------------------------------
# Manejo de JWT
# -----------------------------------------------------------------------------
class TokenDecodeError(Exception):
    """Error al decodificar/validar un token JWT."""


def create_access_token(
    subject: Union[str, int],
    expires_delta: Optional[timedelta] = None,
    **extra: Any,
) -> str:
    """
    Crea un JWT con claim 'sub' y metadatos opcionales en `extra`.
    Por convención, `sub` debe poder mapearse a tu AppUser.id.
    """
    now = datetime.now(tz=timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode: Dict[str, Any] = {"sub": str(subject), "iat": int(now.timestamp()), "exp": int(expire.timestamp())}
    if extra:
        to_encode.update(extra)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodifica y valida un JWT. Lanza TokenDecodeError si es inválido/expirado.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        # Validación mínima del 'sub'
        sub = payload.get("sub")
        if sub is None or not str(sub).strip():
            raise TokenDecodeError("Token sin 'sub'")
        return payload
    except JWTError as e:
        raise TokenDecodeError("Token inválido o expirado") from e
# Fin del archivo