# -*- coding: utf-8 -*-
"""
backend/app/utils/file_cleanup.py

Utilidades para cleanup seguro de archivos temporales en Windows.
Maneja PermissionError y otros problemas relacionados con handlers abiertos.

Autor: DoxAI
Fecha: 06/09/2025
"""

import os
import shutil
import time
import tempfile
import logging
from pathlib import Path
from typing import Optional, Union
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def safe_remove_file(file_path: Union[str, Path], max_attempts: int = 5, delay: float = 0.2) -> bool:
    """
    Remueve un archivo de forma segura con retry logic para Windows.
    
    Args:
        file_path: Ruta del archivo a remover
        max_attempts: Número máximo de intentos
        delay: Tiempo de espera entre intentos (segundos)
        
    Returns:
        bool: True si se removió exitosamente, False si falló
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        return True
    
    for attempt in range(max_attempts):
        try:
            file_path.unlink()
            return True
        except PermissionError as e:
            if attempt < max_attempts - 1:
                logger.debug(f"PermissionError removing {file_path}, attempt {attempt + 1}/{max_attempts}: {e}")
                time.sleep(delay)
            else:
                logger.warning(f"Failed to remove file {file_path} after {max_attempts} attempts: {e}")
                return False
        except FileNotFoundError:
            # File was already removed
            return True
        except Exception as e:
            logger.warning(f"Unexpected error removing file {file_path}: {e}")
            return False
    
    return False


def safe_remove_directory(dir_path: Union[str, Path], max_attempts: int = 5, delay: float = 0.2) -> bool:
    """
    Remueve un directorio de forma segura con retry logic para Windows.
    
    Args:
        dir_path: Ruta del directorio a remover
        max_attempts: Número máximo de intentos
        delay: Tiempo de espera entre intentos (segundos)
        
    Returns:
        bool: True si se removió exitosamente, False si falló
    """
    dir_path = Path(dir_path)
    
    if not dir_path.exists():
        return True
    
    for attempt in range(max_attempts):
        try:
            shutil.rmtree(dir_path)
            return True
        except PermissionError as e:
            if attempt < max_attempts - 1:
                logger.debug(f"PermissionError removing {dir_path}, attempt {attempt + 1}/{max_attempts}: {e}")
                time.sleep(delay)
            else:
                logger.warning(f"Failed to remove directory {dir_path} after {max_attempts} attempts: {e}")
                return False
        except FileNotFoundError:
            # Directory was already removed
            return True
        except Exception as e:
            logger.warning(f"Unexpected error removing directory {dir_path}: {e}")
            return False
    
    return False


@contextmanager
def safe_temp_directory(ignore_cleanup_errors: bool = True, prefix: str = "tmp", suffix: str = ""):
    """
    Context manager para crear y limpiar directorios temporales de forma segura.
    
    Args:
        ignore_cleanup_errors: Si True, no falla si hay errores de cleanup
        prefix: Prefijo para el nombre del directorio temporal
        suffix: Sufijo para el nombre del directorio temporal
        
    Yields:
        Path: Ruta del directorio temporal creado
    """
    temp_dir = None
    try:
        if ignore_cleanup_errors:
            # Use tempfile.TemporaryDirectory with ignore_cleanup_errors if available (Python 3.10+)
            try:
                temp_dir_obj = tempfile.TemporaryDirectory(
                    ignore_cleanup_errors=True, 
                    prefix=prefix, 
                    suffix=suffix
                )
                temp_dir = Path(temp_dir_obj.name)
                with temp_dir_obj:
                    yield temp_dir
                return
            except TypeError:
                # Python < 3.10 doesn't support ignore_cleanup_errors
                pass
        
        # Fallback for older Python versions or when ignore_cleanup_errors=False
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix, suffix=suffix))
        yield temp_dir
        
    finally:
        if temp_dir and temp_dir.exists():
            if ignore_cleanup_errors:
                safe_remove_directory(temp_dir)
            else:
                shutil.rmtree(temp_dir)


@contextmanager
def safe_temp_file(suffix: str = "", prefix: str = "tmp", delete_on_exit: bool = True):
    """
    Context manager para crear archivos temporales con cleanup seguro.
    
    Args:
        suffix: Sufijo para el archivo temporal
        prefix: Prefijo para el archivo temporal
        delete_on_exit: Si True, intenta borrar el archivo al salir
        
    Yields:
        Path: Ruta del archivo temporal creado
    """
    temp_file = None
    try:
        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        os.close(fd)  # Close file descriptor immediately
        temp_file = Path(temp_path)
        yield temp_file
        
    finally:
        if temp_file and delete_on_exit and temp_file.exists():
            safe_remove_file(temp_file)


def write_bytes_safe(file_path: Union[str, Path], data: bytes) -> bool:
    """
    Escribe bytes a un archivo de forma segura, cerrando handlers correctamente.
    
    Args:
        file_path: Ruta del archivo
        data: Datos a escribir
        
    Returns:
        bool: True si se escribió exitosamente
    """
    try:
        file_path = Path(file_path)
        file_path.write_bytes(data)
        return True
    except Exception as e:
        logger.error(f"Error writing bytes to {file_path}: {e}")
        return False


def ensure_closed(obj, close_method: str = "close") -> None:
    """
    Asegura que un objeto se cierre correctamente.
    
    Args:
        obj: Objeto con método de cierre
        close_method: Nombre del método de cierre (default: "close")
    """
    try:
        if obj and hasattr(obj, close_method):
            getattr(obj, close_method)()
    except Exception as e:
        logger.debug(f"Error closing object: {e}")


# Función de compatibilidad para el código existente
def _safe_cleanup_dir(dir_path: str) -> None:
    """Función de compatibilidad - usar safe_remove_directory en su lugar."""
    safe_remove_directory(dir_path)






