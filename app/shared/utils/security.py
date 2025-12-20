# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/security.py

Utilidades de seguridad consolidadas para DoxAI.

Incluye:
- Hasheo y verificación de contraseñas (Argon2id via passlib)
- Generación y validación de tokens JWT
- Helpers para tokens de activación y reset

Autor: DoxAI
Fecha: 2025-10-18 (Consolidación desde utils/security.py + utils/jwt_utils.py)
Actualizado: 2025-12-20 - Migración de bcrypt a Argon2id
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import logging
import uuid

from passlib.context import CryptContext
from jose import JWTError, jwt, ExpiredSignatureError

from app.shared.config import settings

logger = logging.getLogger(__name__)

# ===== PASSWORD HASHING (Argon2id) =====
# Argon2id: resistente a ataques GPU/ASIC, sin límite de 72 bytes
# Límite máximo para prevenir DoS con payloads gigantes
MAX_PASSWORD_LENGTH = 1024

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__type="ID",
    argon2__memory_cost=65536,  # 64 MB
    argon2__time_cost=3,
    argon2__parallelism=2,
)


class PasswordTooLongError(ValueError):
    """Contraseña excede el límite máximo permitido."""
    pass


def hash_password(password: str) -> str:
    """
    Genera un hash seguro de la contraseña usando Argon2id.
    
    Raises:
        PasswordTooLongError: Si la contraseña excede MAX_PASSWORD_LENGTH
    """
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordTooLongError(
            f"La contraseña no puede exceder {MAX_PASSWORD_LENGTH} caracteres"
        )
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica que la contraseña coincida con el hash almacenado.
    
    Returns:
        False si la contraseña es demasiado larga (anti-timing attack)
    """
    if len(plain_password) > MAX_PASSWORD_LENGTH:
        return False  # Fail silently para evitar timing attacks
    return pwd_context.verify(plain_password, hashed_password)


# ===== JWT TOKENS =====
ALGORITHM = "HS256"
JWT_SECRET = settings.jwt_secret
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
ACTIVATION_TOKEN_EXPIRE_MINUTES = settings.activation_token_expire_minutes


def _now_utc() -> datetime:
    """Timestamp UTC actual"""
    return datetime.now(timezone.utc)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    token_type: str = "access",
) -> str:
    """
    Crea un JWT firmado con tipo y expiración.
    
    Args:
        data: Payload del token (ej: {"sub": user_id})
        expires_delta: Duración del token (None = default según tipo)
        token_type: Tipo de token ("access", "activation", "refresh", "password_reset")
    
    Returns:
        Token JWT firmado como string
    """
    to_encode = data.copy()

    if expires_delta is None:
        minutes = ACTIVATION_TOKEN_EXPIRE_MINUTES if token_type == "activation" else ACCESS_TOKEN_EXPIRE_MINUTES
        expires_delta = timedelta(minutes=minutes)

    iat = _now_utc()
    exp = iat + expires_delta

    to_encode.update({
        "exp": exp,
        "iat": iat,
        "jti": str(uuid.uuid4()),
        "token_type": token_type,
    })

    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def create_activation_token(
    user_id: str,
    email: str,
    expires_minutes: Optional[int] = None,
) -> str:
    """
    Helper para generar tokens de activación de cuenta.
    
    Args:
        user_id: ID del usuario (UUID como string)
        email: Email del usuario
        expires_minutes: Minutos de validez (None = default de settings)
    
    Returns:
        Token JWT de activación
    """
    exp_delta = None if expires_minutes is None else timedelta(minutes=expires_minutes)
    payload = {"sub": user_id, "email": email}
    return create_access_token(payload, exp_delta, token_type="activation")


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodifica y valida un JWT.
    
    Args:
        token: Token JWT como string
    
    Returns:
        Payload del token si es válido, None si expiró o es inválido
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except ExpiredSignatureError as e:
        logger.warning(f"Token expirado: {e}")
        return None
    except JWTError as e:
        logger.warning(f"Token inválido: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado al decodificar token: {e}")
        return None


def verify_token_type(token: str, expected_type: str) -> Optional[Dict[str, Any]]:
    """
    Valida un token y verifica que sea del tipo esperado.
    
    Args:
        token: Token JWT como string
        expected_type: Tipo esperado ("access", "activation", etc.)
    
    Returns:
        Payload si es válido y del tipo correcto, None en caso contrario
    """
    payload = decode_token(token)
    if not payload:
        return None
    
    if payload.get("token_type") != expected_type:
        logger.warning(
            f"Tipo de token no coincide: esperado={expected_type}, "
            f"recibido={payload.get('token_type')}"
        )
        return None
    
    return payload


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_activation_token",
    "decode_token",
    "verify_token_type",
    "MAX_PASSWORD_LENGTH",
    "PasswordTooLongError",
]
