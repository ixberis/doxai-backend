# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/storage/pathing.py

Utilidades para normalización y construcción de rutas de storage.
Código puro sin dependencias para facilitar testing.

Autor: Ixchel Beristain
Fecha: 2025-10-26
"""

import re
from pathlib import PurePosixPath
from uuid import UUID

from app.modules.files.facades.errors import FileValidationError


def normalize_storage_path(path: str) -> str:
    """
    Normaliza una ruta de storage para consistencia.
    
    - Convierte a minúsculas
    - Reemplaza espacios y caracteres especiales
    - Colapsa múltiples slashes
    - Elimina leading/trailing slashes
    
    Args:
        path: Ruta a normalizar
        
    Returns:
        Ruta normalizada
        
    Raises:
        FileValidationError: Si la ruta contiene caracteres peligrosos
    """
    if not path:
        raise FileValidationError("Ruta de storage vacía")
    
    # Validar path traversal
    if ".." in path:
        raise FileValidationError("Ruta contiene secuencia de path traversal (..)")
    
    # Normalizar usando PurePosixPath (estándar POSIX para storage)
    normalized = str(PurePosixPath(path))
    
    # Convertir a minúsculas para consistencia
    normalized = normalized.lower()
    
    # Reemplazar espacios y caracteres especiales por guiones
    normalized = re.sub(r'[^a-z0-9/._-]', '-', normalized)
    
    # Colapsar múltiples slashes y guiones
    normalized = re.sub(r'/+', '/', normalized)
    normalized = re.sub(r'-+', '-', normalized)
    
    # Eliminar leading/trailing slashes
    normalized = normalized.strip('/')
    
    return normalized


def build_storage_key(
    project_id: UUID,
    category: str,
    filename: str,
    subfolder: str = ""
) -> str:
    """
    Construye una clave de storage consistente.
    
    Formato: {project_id}/{category}/{subfolder}/{filename}
    
    Args:
        project_id: UUID del proyecto
        category: Categoría de archivo (input/output/temp)
        filename: Nombre del archivo (ya sanitizado)
        subfolder: Subcarpeta opcional (e.g., tipo de producto)
        
    Returns:
        Clave de storage normalizada
        
    Examples:
        >>> build_storage_key(uuid, "input", "doc.pdf")
        "abc-123.../input/doc.pdf"
        
        >>> build_storage_key(uuid, "output", "result.json", "rag")
        "abc-123.../output/rag/result.json"
    """
    parts = [str(project_id), category]
    
    if subfolder:
        parts.append(subfolder)
    
    parts.append(filename)
    
    # Unir y normalizar
    key = "/".join(parts)
    return normalize_storage_path(key)


def validate_path_safety(path: str) -> None:
    """
    Valida que una ruta sea segura para usar en storage.
    
    Previene:
    - Path traversal (..)
    - Rutas absolutas (/path)
    - Caracteres nulos
    - Longitud excesiva
    
    Args:
        path: Ruta a validar
        
    Raises:
        FileValidationError: Si la ruta no es segura
    """
    if not path:
        raise FileValidationError("Ruta vacía")
    
    # Validar longitud máxima (límite común en S3/Azure)
    MAX_PATH_LENGTH = 1024
    if len(path) > MAX_PATH_LENGTH:
        raise FileValidationError(
            f"Ruta excede longitud máxima: {len(path)} > {MAX_PATH_LENGTH}"
        )
    
    # Validar path traversal
    if ".." in path:
        raise FileValidationError("Ruta contiene secuencia de path traversal (..)")
    
    # Validar ruta absoluta
    if path.startswith("/"):
        raise FileValidationError("Ruta no puede ser absoluta (no debe iniciar con /)")
    
    # Validar caracteres nulos
    if "\x00" in path:
        raise FileValidationError("Ruta contiene caracteres nulos")
    
    # Validar caracteres problemáticos para algunos backends
    FORBIDDEN_CHARS = ['\\', '|', '<', '>', '"', '?', '*']
    if any(char in path for char in FORBIDDEN_CHARS):
        raise FileValidationError(
            f"Ruta contiene caracteres no permitidos: {FORBIDDEN_CHARS}"
        )


__all__ = [
    "normalize_storage_path",
    "build_storage_key",
    "validate_path_safety",
]
