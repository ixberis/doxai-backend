
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


class ProjectCloseNotAllowed(Exception):
    """
    Se lanza cuando no se puede cerrar un proyecto por restricciones de estado.
    
    Ejemplo: El proyecto está en state='processing' y no se puede interrumpir.
    """
    def __init__(self, current_state: str, reason: str):
        self.current_state = current_state
        self.reason = reason
        super().__init__(reason)


class ProjectHardDeleteNotAllowed(Exception):
    """
    Se lanza cuando no se puede eliminar definitivamente un proyecto.
    
    RFC-FILES-RETENTION-001: Solo proyectos cerrados pueden eliminarse.
    """
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ProjectHardDeleteAuditFailed(Exception):
    """
    Se lanza cuando falla la inserción del evento de auditoría antes del hard-delete.
    
    El hard-delete NO debe ejecutarse si la auditoría falla.
    Error code estable: PROJECT_HARD_DELETE_AUDIT_FAILED
    
    Atributos adicionales para debug:
    - sqlstate: código SQLSTATE de PostgreSQL (ej: 42501)
    - db_message: mensaje original de la excepción DB
    - exception_type: tipo de excepción original (ej: asyncpg.exceptions.InsufficientPrivilegeError)
    """
    def __init__(
        self, 
        project_id, 
        original_error: str,
        *,
        sqlstate: str = None,
        db_message: str = None,
        exception_type: str = None,
    ):
        self.project_id = project_id
        self.original_error = original_error
        self.error_code = "PROJECT_HARD_DELETE_AUDIT_FAILED"
        self.sqlstate = sqlstate
        self.db_message = db_message
        self.exception_type = exception_type
        super().__init__(f"Error al registrar auditoría para proyecto {project_id}: {original_error}")


__all__ = [
    "ProjectNotFound",
    "InvalidStateTransition",
    "SlugAlreadyExists",
    "FileNotFound",
    "PermissionDenied",
    "ProjectCloseNotAllowed",
    "ProjectHardDeleteNotAllowed",
    "ProjectHardDeleteAuditFailed",
]

# Fin del archivo backend/app/modules/projects/facades/errors.py
