# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/schemas/auth_context_dto.py

DTO mínimo para contexto de autenticación en dependencies.
Contiene solo los campos necesarios para validar auth y poblar request.state.

Autor: DoxAI
Fecha: 2026-01-11
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthContextDTO:
    """
    DTO mínimo para contexto de autenticación.
    
    Solo contiene campos necesarios para:
    - Identificación: user_id, auth_user_id
    - Autorización: role, status
    - Estado: is_activated, is_deleted
    """
    user_id: int
    auth_user_id: UUID
    user_email: str
    user_role: str
    user_status: str
    user_is_activated: bool
    deleted_at: Optional[datetime]
    
    @property
    def is_deleted(self) -> bool:
        """True si el usuario fue soft-deleted."""
        return self.deleted_at is not None
    
    @property
    def is_active(self) -> bool:
        """True si está activado y no eliminado."""
        return self.user_is_activated and not self.is_deleted
    
    @classmethod
    def from_mapping(cls, row: dict) -> "AuthContextDTO":
        """
        Crea AuthContextDTO desde un mapping de fila SQL.
        
        ESTRICTO: Todos los campos son requeridos, sin defaults permisivos.
        
        Raises:
            AuthContextDTOMappingError: Si falta cualquier campo requerido.
        """
        # Todos los campos son requeridos
        required_fields = [
            "user_id", "auth_user_id", "user_email", 
            "user_role", "user_status", "user_is_activated"
        ]
        
        missing = [f for f in required_fields if row.get(f) is None]
        if missing:
            raise AuthContextDTOMappingError(
                f"Campos requeridos faltantes en AuthContextDTO: {missing}"
            )
        
        return cls(
            user_id=row["user_id"],
            auth_user_id=row["auth_user_id"],
            user_email=row["user_email"],
            user_role=row["user_role"],
            user_status=row["user_status"],
            user_is_activated=bool(row["user_is_activated"]),
            deleted_at=row.get("deleted_at"),
        )


class AuthContextDTOMappingError(Exception):
    """Error al mapear fila SQL a AuthContextDTO."""
    pass
