
# -*- coding: utf-8 -*-
"""
backend/app/utils/zip_utils.py

Utilidades auxiliares para la creación y manipulación de archivos ZIP en DoxAI.

Incluye funciones para:
- Agregar archivos al ZIP a partir de bytes o rutas
- Normalizar nombres internos (arcname) dentro del archivo comprimido
- Validaciones simples de estructura o extensión

Autor: Ixchel Beristain
Fecha: 28/06/2025
"""

import zipfile
from typing import Union
from pathlib import Path


def add_bytes_to_zip(
    zip_file: zipfile.ZipFile,
    file_bytes: bytes,
    arcname: str
) -> None:
    """
    Agrega un archivo a un ZIP desde su contenido en bytes.

    Args:
        zip_file: instancia abierta de zipfile.ZipFile en modo escritura.
        file_bytes: contenido del archivo en bytes.
        arcname: nombre con el que se almacenará dentro del ZIP (incluye carpeta interna).
    """
    zip_file.writestr(arcname, file_bytes)


def add_file_to_zip_from_path(
    zip_file: zipfile.ZipFile,
    file_path: Union[str, Path],
    arcname: str = None
) -> None:
    """
    Agrega un archivo existente en disco al ZIP.

    Args:
        zip_file: instancia abierta de zipfile.ZipFile.
        file_path: ruta absoluta o relativa del archivo.
        arcname: nombre alternativo dentro del ZIP. Si no se proporciona, se usa el nombre original.
    """
    path = Path(file_path)
    zip_file.write(path, arcname=arcname or path.name)


def is_valid_zip_extension(file_name: str) -> bool:
    """
    Valida si un nombre de archivo tiene extensión .zip (insensible a mayúsculas).

    Args:
        file_name: nombre del archivo a validar.

    Returns:
        True si termina en .zip, False en caso contrario.
    """
    return file_name.lower().endswith(".zip")
# File: backend/app/utils/zip_utils.py







