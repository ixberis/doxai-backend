# -*- coding: utf-8 -*-
"""
backend/app/utils/file_validation_utils.py

Utilidades para validar archivos cargados por el usuario en DoxAI.

Incluye:
- Validación de tipo de archivo permitido
- Validación de tamaño máximo permitido
- Integración con sistema de sanitización de nombres

Autor: Ixchel Beristain
Fecha: 12/06/2025
Actualizado: 25/09/2025 - Reorganizado para evitar importaciones circulares
"""

from urllib.parse import quote
from fastapi import UploadFile, HTTPException, status
from pathlib import Path

from app.shared.config import settings
from app.modules.files.enums.file_type_enum import FileType
from app.shared.utils.filename_core import sanitize_filename_for_storage


def _get_monitoring_decorator():
    """Lazy import to avoid circular dependencies."""
    try:
        from app.shared.utils.filename_monitoring import monitor_sanitization
        return monitor_sanitization
    except ImportError:
        # Return a no-op decorator if monitoring is not available
        def no_op_decorator(func):
            return func
        return no_op_decorator


def sanitize_filename_with_monitoring(filename: str) -> str:
    """
    Wrapper for sanitize_filename_for_storage that applies monitoring decorator.
    
    Args:
        filename (str): Nombre original del archivo
        
    Returns:
        str: Nombre sanitizado compatible con almacenamiento
    """
    monitor_sanitization = _get_monitoring_decorator()
    
    @monitor_sanitization
    def _perform_sanitization():
        return sanitize_filename_for_storage(filename)
    
    return _perform_sanitization()


def encode_filename_for_download(filename: str) -> str:
    """
    Codifica un nombre de archivo para descarga segura con soporte Unicode.
    
    Primero sanitiza el nombre y luego lo codifica usando URL encoding
    para asegurar compatibilidad con navegadores y caracteres especiales.
    
    Args:
        filename (str): Nombre original del archivo (puede contener acentos, espacios, etc.)
        
    Returns:
        str: Nombre codificado seguro para header Content-Disposition
        
    Example:
        encode_filename_for_download("Evaluación Lingüística.pdf")
        # Returns: "evaluacion-linguistica.pdf" (URL encoded if needed)
    """
    # Primero sanitizar el nombre para remover caracteres problemáticos
    sanitized_name = sanitize_filename_with_monitoring(filename)
    
    # Luego codificar para descarga segura
    return quote(sanitized_name.encode('utf-8'))


def validate_file_type_and_size(file: UploadFile) -> str:
    """
    Valida que el archivo tenga un tipo permitido, no exceda el tamaño máximo
    y retorna el nombre sanitizado para storage.

    Args:
        file (UploadFile): Archivo recibido a través de la API.

    Returns:
        str: Nombre del archivo sanitizado y listo para almacenamiento

    Raises:
        HTTPException: Si el tipo de archivo no está permitido o excede el tamaño máximo.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe tener un nombre válido"
        )
    
    file_extension = file.filename.split(".")[-1].lower()
    file_size = _get_file_size(file)

    if file_extension not in settings.ALLOWED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo no permitido: .{file_extension}"
        )

    if file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo excede el tamaño máximo de {settings.MAX_FILE_SIZE_MB} MB"
        )
    
    # Sanitizar el nombre del archivo para Supabase Storage con monitoreo
    sanitized_filename = sanitize_filename_with_monitoring(file.filename)
    
    return sanitized_filename


def _get_file_size(file: UploadFile) -> int:
    content = file.file.read()
    file.file.seek(0)
    return len(content)


def find_matching_file(directory: Path, visual_hint: str, extension: str) -> Path:
    """
    Busca en un directorio un archivo cuyo nombre contenga la subcadena `visual_hint`
    y cuya extensión coincida (ignorando diferencias Unicode como tildes combinadas).

    Útil para resolver problemas en Windows/OneDrive donde el nombre del archivo contiene
    caracteres Unicode equivalentes visualmente pero distintos binariamente.

    Args:
        directory (Path): Ruta del directorio donde buscar
        visual_hint (str): Parte del nombre visual del archivo (sin extensión)
        extension (str): Extensión esperada, con punto (ej. '.docx')

    Returns:
        Path: Ruta del archivo coincidente

    Raises:
        FileNotFoundError: Si no se encuentra ningún archivo con el criterio dado

    Example:
        >>> find_matching_file(Path("tests/"), "formato mipymes", ".docx")
    """
    normalized_hint = visual_hint.lower().strip()
    normalized_ext = extension.lower()

    for file in directory.iterdir():
        if (
            normalized_hint in file.name.lower()
            and file.suffix.lower() == normalized_ext
        ):
            return file

    raise FileNotFoundError(
        f"❌ No se encontró ningún archivo en '{directory}' con '{visual_hint}' y extensión '{extension}'"
    )

# Fin del archivo file_validation_utils.py






