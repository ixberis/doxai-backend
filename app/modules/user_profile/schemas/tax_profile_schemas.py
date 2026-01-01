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

# ============================================================================
# Catálogos SAT de regímenes fiscales - MUTUAMENTE EXCLUYENTES
# ============================================================================

# Regímenes para Personas Morales (PM) - use_razon_social = True
ALLOWED_REGIMENES_PM = frozenset({
    '601',  # General de Ley Personas Morales
    '603',  # Personas Morales con Fines no Lucrativos
    '607',  # Enajenación o Adquisición de Bienes
    '609',  # Consolidación
    '620',  # Sociedades Cooperativas de Producción que optan por Diferir sus Ingresos
    '622',  # Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras
    '623',  # Opcional para Grupos de Sociedades
    '624',  # Coordinados
    '626',  # RESICO (Régimen Simplificado de Confianza)
    '628',  # Hidrocarburos
})

# Regímenes para Personas Físicas (PF) - use_razon_social = False
# Lista EXPLÍCITA (NO es complemento de PM)
ALLOWED_REGIMENES_PF = frozenset({
    '605',  # Sueldos y Salarios e Ingresos Asimilados a Salarios
    '606',  # Arrendamiento
    '608',  # Demás ingresos
    '610',  # Residentes en el Extranjero sin Establecimiento Permanente en México
    '611',  # Ingresos por Dividendos (socios y accionistas)
    '612',  # Personas Físicas con Actividades Empresariales y Profesionales
    '614',  # Ingresos por intereses
    '615',  # Régimen de los ingresos por obtención de premios
    '616',  # Sin obligaciones fiscales
    '621',  # Incorporación Fiscal
    '625',  # Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas
})

# Catálogo unificado (para validación general de clave SAT válida)
ALLOWED_REGIMENES = ALLOWED_REGIMENES_PM | ALLOWED_REGIMENES_PF

# Guard: verificar exclusión mutua en tiempo de carga
_intersection = ALLOWED_REGIMENES_PM & ALLOWED_REGIMENES_PF
if _intersection:
    raise RuntimeError(f"SAT regime keys present in both PF and PM catalogs: {_intersection}")


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
        """Valida que la clave exista en el catálogo SAT (PF o PM)."""
        if v is None or v == "":
            return None
        v = v.strip()
        if v not in ALLOWED_REGIMENES:
            raise ValueError("Régimen fiscal inválido (clave SAT no reconocida)")
        return v
    
    @model_validator(mode='after')
    def validate_razon_social_and_regimen_consistency(self) -> 'TaxProfileBase':
        """
        Valida:
        1. Si use_razon_social=True, razon_social no puede estar vacío.
        2. Si hay régimen fiscal, debe ser compatible con el tipo (PM vs PF).
        """
        # Validar razon_social requerida para PM
        if self.use_razon_social:
            if not self.razon_social or not self.razon_social.strip():
                raise ValueError(
                    "Razón social es obligatoria cuando 'Tengo razón social' está activado."
                )
        
        # Validar consistencia régimen vs tipo (PM/PF)
        if self.regimen_fiscal_clave:
            if self.use_razon_social:
                # PM: régimen debe estar en catálogo PM
                if self.regimen_fiscal_clave not in ALLOWED_REGIMENES_PM:
                    raise ValueError(
                        f"Régimen fiscal '{self.regimen_fiscal_clave}' no es válido para Persona Moral. "
                        f"Claves permitidas: {sorted(ALLOWED_REGIMENES_PM)}"
                    )
            else:
                # PF: régimen debe estar en catálogo PF
                if self.regimen_fiscal_clave not in ALLOWED_REGIMENES_PF:
                    raise ValueError(
                        f"Régimen fiscal '{self.regimen_fiscal_clave}' no es válido para Persona Física. "
                        f"Claves permitidas: {sorted(ALLOWED_REGIMENES_PF)}"
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
    "ALLOWED_REGIMENES",
    "ALLOWED_REGIMENES_PM",
    "ALLOWED_REGIMENES_PF",
]
