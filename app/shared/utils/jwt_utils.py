
# -*- coding: utf-8 -*-
"""
backend/app/utils/jwt_utils.py

JWT helpers para DoxAI:
- create_access_token(data, expires_delta?, token_type?)
- create_activation_token(user_id, email, expires_minutes?)
- decode_token(token)
- verify_token_type(token, expected_type)

Autor: Ixchel Beristain
Actualizado: 2025-10-16
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt, ExpiredSignatureError
import logging
import uuid

from app.shared.config import settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
ACTIVATION_TOKEN_EXPIRE_MINUTES = settings.activation_token_expire_minutes
JWT_SECRET = settings.jwt_secret


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    token_type: str = "access",
) -> str:
    """
    Crea un JWT firmado con tipo y expiración.
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
    Helper para tokens de activación estandarizados.
    """
    exp_delta = None if expires_minutes is None else timedelta(minutes=expires_minutes)
    payload = {"sub": user_id, "email": email}
    return create_access_token(payload, exp_delta, token_type="activation")


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodifica y valida un JWT. Devuelve None si es inválido o expiró.
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
    Devuelve el payload si el token es válido y del tipo esperado; de lo contrario, None.
    """
    payload = decode_token(token)
    if not payload:
        return None
    if payload.get("token_type") != expected_type:
        logger.warning("Tipo de token no coincide: esperado=%s, recibido=%s", expected_type, payload.get("token_type"))
        return None
    return payload
# Fin del módulo jwt_utils.py







