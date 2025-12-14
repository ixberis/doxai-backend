
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/facades/errors.py

Excepciones de dominio para el módulo de proyectos.
Facilita el manejo de errores en facades y servicios.

Autor: Ixchel Beristáin
Fecha: 2025-10-26
"""


class ProjectNotFound(Exception):
    """Se lanza cuando no se encuentra un proyecto por ID o slug."""
    def __init__(self, identifier):
        self.identifier = identifier
        super().__init__(f"Proyecto no encontrado: {identifier}")


class InvalidStateTransition(Exception):
    """Se lanza cuando se intenta una transición de estado inválida."""
    def __init__(self, from_state, to_state, message=None):
        self.from_state = from_state
        self.to_state = to_state
        default_msg = f"Transición inválida: {from_state} → {to_state}"
        super().__init__(message or default_msg)


class SlugAlreadyExists(Exception):
    """Se lanza cuando se intenta crear un proyecto con slug duplicado."""
    def __init__(self, slug):
        self.slug = slug
        super().__init__(f"El slug ya existe: {slug}")


class FileNotFound(Exception):
    """Se lanza cuando no se encuentra un archivo de proyecto por ID."""
    def __init__(self, file_id):
        self.file_id = file_id
        super().__init__(f"Archivo no encontrado: {file_id}")


class PermissionDenied(Exception):
    """Se lanza cuando un usuario no tiene permisos para una operación."""
    def __init__(self, message: str):
        super().__init__(message)


__all__ = [
    "ProjectNotFound",
    "InvalidStateTransition",
    "SlugAlreadyExists",
    "FileNotFound",
    "PermissionDenied",
]

# Fin del archivo backend/app/modules/projects/facades/errors.py
