# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/routes/tax_profile_routes.py

Rutas para gestión de perfil fiscal.

Endpoints:
- GET /api/profile/tax-profile
- PUT /api/profile/tax-profile (upsert)

Autor: DoxAI
Fecha: 2025-12-31
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.modules.auth.services import get_current_user
from app.shared.auth_context import extract_user_id

from ..models.tax_profile import UserTaxProfile, TaxProfileStatus
from ..schemas.tax_profile_schemas import (
    TaxProfileUpsertRequest,
    TaxProfileResponse,
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


__all__ = ["router"]
