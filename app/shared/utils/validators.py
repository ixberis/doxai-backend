# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/validators.py

Validadores comunes para la aplicación DoxAI.

Incluye validación de:
- Email
- Teléfono
- Contraseñas (fortaleza)
- UUIDs
- Sanitización de strings

Autor: DoxAI
Fecha: 2025-10-18
"""

import re
from typing import Optional
from uuid import UUID


def validate_email(email: str) -> bool:
    """
    Valida formato de email básico.
    
    Args:
        email: String de email a validar
    
    Returns:
        True si el formato es válido, False en caso contrario
    """
    if not email or not isinstance(email, str):
        return False
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def validate_phone(phone: str) -> bool:
    """
    Valida formato de teléfono internacional básico.
    Permite: dígitos, +, (), espacios, guiones
    Longitud: 7-20 caracteres
    
    Args:
        phone: String de teléfono a validar
    
    Returns:
        True si el formato es válido, False en caso contrario
    """
    if not phone or not isinstance(phone, str):
        return False
    
    pattern = r'^[0-9+() -]{7,20}$'
    return bool(re.match(pattern, phone.strip()))


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Valida fortaleza de contraseña según políticas de DoxAI.
    
    Requisitos:
    - Mínimo 8 caracteres
    - Al menos una mayúscula
    - Al menos una minúscula
    - Al menos un número
    - Al menos un carácter especial
    
    Args:
        password: Contraseña a validar
    
    Returns:
        Tuple (es_válida, mensaje_error)
    """
    if not password or not isinstance(password, str):
        return False, "La contraseña no puede estar vacía"
    
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if not re.search(r'[A-Z]', password):
        return False, "La contraseña debe contener al menos una mayúscula"
    
    if not re.search(r'[a-z]', password):
        return False, "La contraseña debe contener al menos una minúscula"
    
    if not re.search(r'[0-9]', password):
        return False, "La contraseña debe contener al menos un número"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "La contraseña debe contener al menos un carácter especial"
    
    return True, None


def validate_uuid(value: str) -> bool:
    """
    Valida que un string sea un UUID válido.
    
    Args:
        value: String a validar
    
    Returns:
        True si es un UUID válido, False en caso contrario
    """
    if not value or not isinstance(value, str):
        return False
    
    try:
        UUID(value.strip())
        return True
    except (ValueError, AttributeError):
        return False


def sanitize_string(value: str, max_length: Optional[int] = None) -> str:
    """
    Sanitiza un string eliminando espacios extras y caracteres de control.
    
    Args:
        value: String a sanitizar
        max_length: Longitud máxima (None = sin límite)
    
    Returns:
        String sanitizado
    """
    if not value or not isinstance(value, str):
        return ""
    
    # Eliminar espacios al inicio/final
    sanitized = value.strip()
    
    # Eliminar caracteres de control (excepto \n y \t)
    sanitized = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', sanitized)
    
    # Normalizar espacios múltiples a uno solo
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Limitar longitud si se especifica
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized


__all__ = [
    "validate_email",
    "validate_phone",
    "validate_password_strength",
    "validate_uuid",
    "sanitize_string",
]
