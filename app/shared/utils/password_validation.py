
"""
backend/app/utils/security/password_validation.py

Funciones para validar la seguridad de contraseñas en DoxAI.

Incluye:
- Validación de complejidad de contraseñas según requisitos mínimos de seguridad.

Autor: Ixchel Beristain
Fecha: 31/05/2025
"""


import re
import logging

logger = logging.getLogger(__name__)

def validate_password_complexity(password: str) -> bool:
    """
    Validar complejidad de contraseña

    Requisitos:
    - Entre 12 y 24 caracteres
    - Al menos una letra mayúscula
    - Al menos una letra minúscula
    - Al menos un número
    - Al menos un carácter especial (#$%"&_-)
    """
    if len(password) < 12 or len(password) > 24:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'[0-9]', password):
        return False
    if not re.search(r'[#$%"&_\-]', password):
        return False
    return True







