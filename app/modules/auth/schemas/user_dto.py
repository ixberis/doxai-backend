# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/schemas/user_dto.py

DTO (Data Transfer Object) para usuarios - usado en modo Core sin ORM.
Estructura ligera sin overhead de SQLAlchemy ORM.

Autor: Ixchel Beristain
Fecha: 2025-01-11
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.modules.auth.enums import UserStatus


@dataclass(frozen=True, slots=True)
class UserDTO:
    """
    DTO inmutable para representar un usuario sin ORM overhead.
    Usado por modo Core en get_by_email para comparar rendimiento.
    """
    user_id: int
    auth_user_id: UUID
    user_email: str
    user_name: Optional[str]
    user_password_hash: str
    user_status: UserStatus
    user_created_at: datetime
    user_updated_at: Optional[datetime]
    deleted_at: Optional[datetime]
    welcome_email_status: Optional[str]
    welcome_email_sent_at: Optional[datetime]
    welcome_email_attempts: int
    welcome_email_claimed_at: Optional[datetime]
    welcome_email_last_error: Optional[str]
    
    @classmethod
    def from_mapping(cls, row: dict) -> "UserDTO":
        """Construye DTO desde un dict (resultado de mappings().first())."""
        return cls(
            user_id=row["user_id"],
            auth_user_id=row["auth_user_id"],
            user_email=row["user_email"],
            user_name=row.get("user_name"),
            user_password_hash=row["user_password_hash"],
            user_status=row["user_status"],
            user_created_at=row["user_created_at"],
            user_updated_at=row.get("user_updated_at"),
            deleted_at=row.get("deleted_at"),
            welcome_email_status=row.get("welcome_email_status"),
            welcome_email_sent_at=row.get("welcome_email_sent_at"),
            welcome_email_attempts=row.get("welcome_email_attempts", 0),
            welcome_email_claimed_at=row.get("welcome_email_claimed_at"),
            welcome_email_last_error=row.get("welcome_email_last_error"),
        )


__all__ = ["UserDTO"]
