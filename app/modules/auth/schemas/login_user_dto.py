# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/schemas/login_user_dto.py

DTO mínimo para login - evita overhead ORM con query storm de 32 statements.
Solo incluye los campos necesarios para validar credenciales y estado.

SEGURIDAD: Campos críticos son OBLIGATORIOS y fallan fuerte si no están.

Autor: DoxAI
Fecha: 2026-01-11
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


class LoginUserDTOMappingError(ValueError):
    """Error cuando faltan campos obligatorios en el mapping."""
    pass


@dataclass(frozen=True, slots=True)
class LoginUserDTO:
    """
    DTO mínimo e inmutable para validación de login.
    Campos exactos requeridos para:
    - Validar password hash
    - Verificar estado de cuenta (activated, deleted)
    - Emitir JWT con auth_user_id
    
    SEGURIDAD: Campos críticos son obligatorios. Si faltan, from_mapping() falla.
    """
    user_id: int
    auth_user_id: Optional[UUID]  # Puede ser None en legacy (se genera on-the-fly)
    user_email: str
    user_password_hash: str
    user_role: str
    user_status: str
    user_is_activated: bool
    deleted_at: Optional[datetime]
    # Campos adicionales para compatibilidad con response
    user_full_name: Optional[str] = None
    
    @classmethod
    def from_mapping(cls, row: dict) -> "LoginUserDTO":
        """
        Construye DTO desde un dict (resultado de mappings().first()).
        
        SEGURIDAD: Campos críticos son OBLIGATORIOS.
        Si falta user_id, user_email, user_password_hash, user_role, 
        user_status, o user_is_activated, lanza LoginUserDTOMappingError.
        
        Campos opcionales:
        - auth_user_id: Puede ser None (legacy, se genera on-the-fly)
        - deleted_at: Puede ser None (usuario activo)
        - user_full_name: Puede ser None
        
        Raises:
            LoginUserDTOMappingError: Si falta algún campo obligatorio
        """
        # Validar campos obligatorios - FALLAR FUERTE si no están
        required_fields = ["user_id", "user_email", "user_password_hash", 
                          "user_role", "user_status", "user_is_activated"]
        missing = [f for f in required_fields if f not in row]
        if missing:
            raise LoginUserDTOMappingError(
                f"LoginUserDTO: faltan campos obligatorios: {missing}"
            )
        
        # Campos críticos: NO defaults permisivos, usar valor directo
        return cls(
            user_id=row["user_id"],
            auth_user_id=row.get("auth_user_id"),  # Puede ser None (legacy)
            user_email=row["user_email"],
            user_password_hash=row["user_password_hash"],
            user_role=str(row["user_role"]),  # Obligatorio, sin default
            user_status=str(row["user_status"]),  # Obligatorio, sin default
            user_is_activated=bool(row["user_is_activated"]),  # Obligatorio
            deleted_at=row.get("deleted_at"),  # Opcional: None = no eliminado
            user_full_name=row.get("user_full_name"),  # Opcional
        )
    
    @property
    def is_deleted(self) -> bool:
        """True si el usuario está marcado como eliminado."""
        return self.deleted_at is not None
    
    @property
    def can_login(self) -> bool:
        """True si el usuario puede hacer login (activado y no eliminado)."""
        return self.user_is_activated and not self.is_deleted


__all__ = ["LoginUserDTO", "LoginUserDTOMappingError"]
