# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/http_exceptions.py

Excepciones HTTP personalizadas para la API de DoxAI.
Estandariza respuestas de error con códigos HTTP apropiados.

Autor: DoxAI
Fecha: 2025-10-18
"""

from fastapi import HTTPException, status
from typing import Any, Dict, Optional


class BadRequestException(HTTPException):
    """400 - Solicitud mal formada o parámetros inválidos"""
    def __init__(
        self,
        detail: str = "Solicitud inválida",
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            headers=headers
        )


class UnauthorizedException(HTTPException):
    """401 - Autenticación requerida o credenciales inválidas"""
    def __init__(
        self,
        detail: str = "No autorizado - credenciales inválidas o ausentes",
        headers: Optional[Dict[str, Any]] = None
    ):
        if headers is None:
            headers = {"WWW-Authenticate": "Bearer"}
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers=headers
        )


class ForbiddenException(HTTPException):
    """403 - Acceso prohibido - usuario autenticado pero sin permisos"""
    def __init__(
        self,
        detail: str = "Acceso prohibido - permisos insuficientes",
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            headers=headers
        )


class NotFoundException(HTTPException):
    """404 - Recurso no encontrado"""
    def __init__(
        self,
        detail: str = "Recurso no encontrado",
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            headers=headers
        )


class ConflictException(HTTPException):
    """409 - Conflicto con el estado actual del recurso"""
    def __init__(
        self,
        detail: str = "Conflicto - el recurso ya existe o hay un conflicto de estado",
        error_code: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None
    ):
        # Build structured detail with error_code if provided
        if error_code:
            structured_detail = {
                "detail": detail,
                "error_code": error_code
            }
            super().__init__(
                status_code=status.HTTP_409_CONFLICT,
                detail=structured_detail,
                headers=headers
            )
        else:
            super().__init__(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail,
                headers=headers
            )


class UnprocessableEntityException(HTTPException):
    """422 - La sintaxis es correcta pero la semántica es errónea"""
    def __init__(
        self,
        detail: str = "Entidad no procesable - validación semántica fallida",
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            headers=headers
        )


class InternalServerException(HTTPException):
    """500 - Error interno del servidor"""
    def __init__(
        self,
        detail: str = "Error interno del servidor",
        headers: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            headers=headers
        )


__all__ = [
    "BadRequestException",
    "UnauthorizedException",
    "ForbiddenException",
    "NotFoundException",
    "ConflictException",
    "UnprocessableEntityException",
    "InternalServerException",
]
