# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/schemas/tax_profile_schemas.py

Schemas Pydantic para perfil fiscal.

Autor: DoxAI
Fecha: 2025-12-31
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Regex para RFC mexicano (persona física: 13 chars, moral: 12 chars)
RFC_PATTERN = re.compile(r'^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$', re.IGNORECASE)

# Regex para código postal (5 dígitos)
CP_PATTERN = re.compile(r'^\d{5}$')

# Catálogo SAT de regímenes fiscales permitidos
ALLOWED_REGIMENES = frozenset({
    '601', '603', '605', '606', '607', '608', '610', '611', '612',
    '614', '615', '616', '620', '621', '622', '623', '624', '625', '626',
})


class TaxProfileBase(BaseModel):
    """Campos base del perfil fiscal."""
    
    rfc: Optional[str] = Field(
        None, 
        max_length=13,
        description="RFC del contribuyente (12-13 caracteres)"
    )
    razon_social: Optional[str] = Field(
        None, 
        max_length=255,
        description="Razón social o nombre fiscal"
    )
    use_razon_social: bool = Field(
        False,
        description="Si true, usar razón social en recibos (Persona Moral); si false, usar nombre del usuario."
    )
    regimen_fiscal_clave: Optional[str] = Field(
        None, 
        max_length=10,
        description="Clave de régimen fiscal SAT (ej: 601, 612, 626)"
    )
    domicilio_fiscal_cp: Optional[str] = Field(
        None, 
        max_length=5,
        description="Código postal del domicilio fiscal (5 dígitos)"
    )
    domicilio_calle: Optional[str] = Field(None, max_length=255)
    domicilio_num_ext: Optional[str] = Field(None, max_length=20)
    domicilio_num_int: Optional[str] = Field(None, max_length=20)
    domicilio_colonia: Optional[str] = Field(None, max_length=100)
    domicilio_municipio: Optional[str] = Field(None, max_length=100)
    domicilio_estado: Optional[str] = Field(None, max_length=50)
    domicilio_pais: Optional[str] = Field("MX", max_length=50)
    email_facturacion: Optional[str] = Field(None, max_length=255)
    uso_cfdi_default: Optional[str] = Field(None, max_length=10)
    
    @field_validator('rfc')
    @classmethod
    def validate_rfc(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.upper().strip()
        if not RFC_PATTERN.match(v):
            raise ValueError(
                "RFC inválido. Formato esperado: XXXX000000XXX (persona moral) "
                "o XXXX000000XXX (persona física)"
            )
        return v
    
    @field_validator('domicilio_fiscal_cp')
    @classmethod
    def validate_cp(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip()
        if not CP_PATTERN.match(v):
            raise ValueError("Código postal inválido. Debe ser 5 dígitos.")
        return v
    
    @field_validator('regimen_fiscal_clave')
    @classmethod
    def validate_regimen(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        v = v.strip()
        if v not in ALLOWED_REGIMENES:
            raise ValueError("Régimen fiscal inválido (clave SAT no reconocida)")
        return v
    
    @model_validator(mode='after')
    def validate_razon_social_required(self) -> 'TaxProfileBase':
        """Si use_razon_social=True, razon_social no puede estar vacío."""
        if self.use_razon_social:
            if not self.razon_social or not self.razon_social.strip():
                raise ValueError(
                    "Razón social es obligatoria cuando 'Tengo razón social' está activado."
                )
        return self


class TaxProfileUpsertRequest(TaxProfileBase):
    """Request para crear/actualizar perfil fiscal."""
    pass


class TaxProfileResponse(TaxProfileBase):
    """Respuesta con datos del perfil fiscal."""
    
    id: int
    user_id: int
    status: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TaxProfileSummary(BaseModel):
    """Resumen corto del perfil fiscal (para recibos)."""
    
    rfc: Optional[str] = None
    razon_social: Optional[str] = None
    regimen_fiscal_clave: Optional[str] = None
    domicilio_fiscal_cp: Optional[str] = None
    domicilio_completo: Optional[str] = None
    email_facturacion: Optional[str] = None


__all__ = [
    "TaxProfileBase",
    "TaxProfileUpsertRequest",
    "TaxProfileResponse",
    "TaxProfileSummary",
]
