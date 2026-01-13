# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/models/tax_profile.py

Modelo ORM para user_tax_profiles.

Almacena datos fiscales del usuario para recibos y futura facturación CFDI.

BD 2.0 SSOT (2026-01-11):
- auth_user_id (UUID): identificador canónico de ownership
- user_id (int): FK legacy para JOINs internos

Autor: DoxAI
Fecha: 2025-12-31
Actualizado: 2026-01-11 - BD 2.0 SSOT auth_user_id
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    String,
    BigInteger,
    DateTime,
    Text,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class TaxProfileStatus(str, Enum):
    """Estados del perfil fiscal."""
    DRAFT = "draft"
    ACTIVE = "active"
    VERIFIED = "verified"


class UserTaxProfile(Base):
    """
    Perfil fiscal del usuario.
    
    Almacena RFC, razón social, dirección fiscal y datos
    necesarios para recibos y futura facturación CFDI.
    
    BD 2.0 SSOT: auth_user_id es el identificador canónico de ownership.
    """
    
    __tablename__ = "user_tax_profiles"
    
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    
    # BD 2.0 SSOT: auth_user_id (UUID) es el identificador canónico
    # DB schema: NOT NULL UNIQUE (required for FK constraint)
    auth_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,  # Alineado con DB: NOT NULL
        unique=True,
        index=True,
        doc="UUID del usuario (BD 2.0 SSOT).",
    )
    
    # FK legacy a app_users.user_id (para JOINs internos)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
        doc="ID legacy del usuario (relación 1:1).",
    )
    
    # RFC (Registro Federal de Contribuyentes)
    rfc: Mapped[Optional[str]] = mapped_column(
        String(13),
        nullable=True,
        doc="RFC del contribuyente (12-13 caracteres).",
    )
    
    # Razón social / Nombre fiscal
    razon_social: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Razón social o nombre fiscal.",
    )
    
    # Régimen fiscal clave SAT
    regimen_fiscal_clave: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        doc="Clave de régimen fiscal SAT (ej: 601, 612, 626).",
    )
    
    # Código postal fiscal (5 dígitos)
    domicilio_fiscal_cp: Mapped[Optional[str]] = mapped_column(
        String(5),
        nullable=True,
        doc="Código postal del domicilio fiscal.",
    )
    
    # Domicilio fiscal completo (opcional)
    domicilio_calle: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Calle del domicilio fiscal.",
    )
    
    domicilio_num_ext: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Número exterior.",
    )
    
    domicilio_num_int: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Número interior.",
    )
    
    domicilio_colonia: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Colonia.",
    )
    
    domicilio_municipio: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Municipio o delegación.",
    )
    
    domicilio_estado: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Estado.",
    )
    
    domicilio_pais: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        default="MX",
        doc="País (ISO 2 letras).",
    )
    
    # Email para facturación (puede ser diferente al principal)
    email_facturacion: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Email para envío de facturas.",
    )
    
    # Flag: ¿usar razón social en recibos? (Persona Moral)
    use_razon_social: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        doc="Si true, usar razon_social en recibos; si false, usar nombre del usuario.",
    )
    
    # Uso CFDI predeterminado (para futuro)
    uso_cfdi_default: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        doc="Clave de uso CFDI predeterminado (ej: G03).",
    )
    
    # Estado del perfil
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TaxProfileStatus.DRAFT.value,
        doc="Estado: draft, active, verified.",
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    
    def __repr__(self) -> str:
        return f"<UserTaxProfile id={self.id} user={self.user_id} rfc={self.rfc} status={self.status}>"


__all__ = ["UserTaxProfile", "TaxProfileStatus"]
