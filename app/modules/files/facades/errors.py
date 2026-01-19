
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/facades/errors.py

Errores de dominio para las fachadas del módulo Files.

Objetivo:
- Definir excepciones semánticas que las fachadas y utilidades (p.ej.
  validadores) pueden lanzar.
- Permitir que los ruteadores (o módulos clientes) traduzcan estas
  excepciones a respuestas HTTP adecuadas sin acoplarse a FastAPI.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

from __future__ import annotations


class FilesError(Exception):
    """
    Error base para el módulo Files.
    """

    pass


class FileNotFoundError(FilesError):
    """
    El archivo solicitado no existe o no es accesible para el usuario.
    """

    def __init__(self, message: str = "File not found") -> None:
        super().__init__(message)


class FileAccessDeniedError(FilesError):
    """
    El usuario no tiene permisos para acceder al archivo.
    """

    def __init__(self, message: str = "Access to file is denied") -> None:
        super().__init__(message)


class FileStorageError(FilesError):
    """
    Error al interactuar con el storage (upload/download/delete).
    """

    def __init__(self, message: str = "Storage operation failed") -> None:
        super().__init__(message)


class InvalidFileOperationError(FilesError):
    """
    Operación inválida sobre un archivo dado su estado actual.
    """

    def __init__(self, message: str = "Invalid operation for file") -> None:
        super().__init__(message)


class FileValidationError(FilesError):
    """
    Error genérico de validación de archivo (tamaño, checksum, formato, etc.).
    """

    def __init__(self, message: str = "File validation failed") -> None:
        super().__init__(message)


class InvalidFileType(FileValidationError):
    """
    El tipo de archivo (extensión/MIME/FileType) no es válido o no coincide
    con las reglas de la plataforma.
    
    Hereda de FileValidationError para que el endpoint capture correctamente
    esta excepción y retorne HTTP 400 (no 500).
    """

    def __init__(self, message: str = "Invalid file type") -> None:
        super().__init__(message)


class StoragePathCollision(FilesError):
    """
    Se lanza cuando la ruta de almacenamiento ya está ocupada por otro archivo.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"Storage path collision at: {path}")


__all__ = [
    "FilesError",
    "FileNotFoundError",
    "FileAccessDeniedError",
    "FileStorageError",
    "InvalidFileOperationError",
    "InvalidFileType",
    "FileValidationError",
    "StoragePathCollision",
]

# Fin del archivo backend/app/modules/files/facades/errors.py