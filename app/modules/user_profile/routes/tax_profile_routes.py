# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/routes/tax_profile_routes.py

Rutas para gestión de perfil fiscal.

Endpoints:
- GET /api/profile/tax-profile
- PUT /api/profile/tax-profile (upsert)
- POST /api/profile/tax-profile/cedula (upload para extracción)

Autor: DoxAI
Fecha: 2025-12-31
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.modules.auth.services import get_current_user
from app.shared.auth_context import extract_user_id

from ..models.tax_profile import UserTaxProfile, TaxProfileStatus
from ..schemas.tax_profile_schemas import (
    TaxProfileUpsertRequest,
    TaxProfileResponse,
    CedulaUploadResponse,
)

router = APIRouter(tags=["Tax Profile"])
logger = logging.getLogger(__name__)


@router.get(
    "/tax-profile",
    response_model=Optional[TaxProfileResponse],
    summary="Obtener perfil fiscal",
    description="Obtiene el perfil fiscal del usuario autenticado. Retorna null si no existe.",
)
async def get_tax_profile(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[TaxProfileResponse]:
    """Obtiene el perfil fiscal del usuario."""
    user_id = extract_user_id(user)
    
    result = await db.execute(
        select(UserTaxProfile).where(UserTaxProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    
    if profile is None:
        return None
    
    return TaxProfileResponse.model_validate(profile)


@router.put(
    "/tax-profile",
    response_model=TaxProfileResponse,
    summary="Crear o actualizar perfil fiscal",
    description="Crea o actualiza el perfil fiscal del usuario (upsert).",
)
async def upsert_tax_profile(
    data: TaxProfileUpsertRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaxProfileResponse:
    """Crea o actualiza el perfil fiscal."""
    user_id = extract_user_id(user)
    
    # Buscar perfil existente
    result = await db.execute(
        select(UserTaxProfile).where(UserTaxProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    
    if profile is None:
        # Crear nuevo
        profile = UserTaxProfile(
            user_id=user_id,
            status=TaxProfileStatus.DRAFT.value,
        )
        db.add(profile)
    
    # Actualizar campos
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    
    # Actualizar status a active si hay RFC y régimen
    if profile.rfc and profile.regimen_fiscal_clave:
        profile.status = TaxProfileStatus.ACTIVE.value
    
    await db.commit()
    await db.refresh(profile)
    
    logger.info("Tax profile upserted: user=%s rfc=%s status=%s", user_id, profile.rfc, profile.status)
    
    return TaxProfileResponse.model_validate(profile)


@router.post(
    "/tax-profile/cedula",
    response_model=CedulaUploadResponse,
    summary="Subir cédula fiscal para extracción",
    description="""
    Sube un PDF de cédula fiscal para extraer datos automáticamente.
    
    El sistema intentará extraer: RFC, razón social, régimen fiscal, 
    código postal y domicilio.
    
    Los campos extraídos se devuelven como propuesta - el usuario
    debe confirmar/editar antes de guardar con PUT /tax-profile.
    """,
)
async def upload_cedula_fiscal(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CedulaUploadResponse:
    """
    Procesa cédula fiscal y extrae datos.
    
    Por ahora retorna campos vacíos para captura manual.
    La extracción automática se implementará con RAG/OCR.
    """
    user_id = extract_user_id(user)
    
    # Validar tipo de archivo
    if file.content_type not in ["application/pdf", "image/jpeg", "image/png"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_file_type",
                "message": "Solo se aceptan archivos PDF, JPG o PNG.",
            },
        )
    
    # Validar tamaño (máx 10MB)
    file_size = 0
    content = await file.read()
    file_size = len(content)
    
    if file_size > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "file_too_large",
                "message": "El archivo excede el límite de 10MB.",
            },
        )
    
    logger.info(
        "Cedula upload: user=%s filename=%s size=%d",
        user_id, file.filename, file_size,
    )
    
    # TODO: Implementar extracción con RAG/OCR
    # Por ahora retornamos campos vacíos para captura manual
    
    # Placeholder: en el futuro aquí iría:
    # 1. Guardar archivo en storage
    # 2. Procesar con OCR si es imagen/escaneado
    # 3. Extraer texto y usar RAG/regex para campos
    # 4. Retornar propuesta con confianza
    
    return CedulaUploadResponse(
        success=True,
        message="Archivo recibido. Por favor completa los datos manualmente.",
        extracted_fields=None,
        confidence=None,
        requires_review=True,
    )


__all__ = ["router"]
