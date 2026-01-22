# -*- coding: utf-8 -*-
"""
backend/app/shared/utils/storage_errors.py

Excepciones semánticas para operaciones de Storage.

Autor: DoxAI
Fecha: 2026-01-22
"""

from __future__ import annotations

from typing import Optional


class StorageRequestError(Exception):
    """
    Error de request a Supabase Storage (400/401/403/5xx).
    
    NO usar para 404 (archivo no encontrado) - usar FileNotFoundError.
    
    Attributes:
        status_code: Código HTTP de la respuesta
        url: URL de la request (sin query string)
        bucket: Nombre del bucket
        path: Path del archivo
        body_snippet: Primeros 300 chars del body de error
    """
    
    def __init__(
        self,
        status_code: int,
        url: str,
        bucket: str,
        path: str,
        body_snippet: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        self.status_code = status_code
        self.url = url.split("?")[0] if url else ""  # Remove query string
        self.bucket = bucket
        self.path = path
        self.body_snippet = (body_snippet or "")[:300]
        
        msg = message or f"Storage request failed: HTTP {status_code}"
        super().__init__(msg)
    
    def to_dict(self) -> dict:
        """Serializa el error para respuestas JSON."""
        return {
            "error": "storage_error",
            "status_code": self.status_code,
            "bucket": self.bucket,
            "path": self.path,
            "message": str(self),
        }


__all__ = ["StorageRequestError"]
