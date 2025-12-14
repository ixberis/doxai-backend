
# -*- coding: utf-8 -*-
"""
backend/app/utils/email_utils.py

Validación y normalización básica de direcciones de correo.
Usa la librería oficial `email-validator` (Pydantic v2 la usa internamente).

Funciones:
- is_valid_email_address(email: str) -> bool
- normalize_email(email: str) -> str

Autor: Ixchel Beristain
Actualizado: 2025-10-16
"""

from typing import Optional
from email_validator import validate_email, EmailNotValidError


def is_valid_email_address(email: Optional[str]) -> bool:
    """Devuelve True si el email cumple formato RFC y dominio válido."""
    if not email:
        return False
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def normalize_email(email: Optional[str]) -> str:
    """
    Normaliza: strip + lowercase del local@domain.
    No valida – combínalo con is_valid_email_address si es necesario.
    """
    return (email or "").strip().lower()
# --- Fin del archivo ---






