# -*- coding: utf-8 -*-
"""
backend/app/modules/user_profile/routes/tax_profile_routes.py

Rutas para gestión de perfil fiscal.

Endpoints:
- GET /api/profile/tax-profile
- PUT /api/profile/tax-profile (upsert)

OPTIMIZADO (2026-01-11):
- Usa get_current_user_ctx (Core) para auth (~40ms vs ~1200ms ORM)
- Usa RequestTelemetry para instrumentación canónica
- BD 2.0 SSOT: auth_user_id como identificador de ownership

Autor: DoxAI
Fecha: 2025-12-31
Actualizado: 2026-01-11 - Core ctx + RequestTelemetry + BD 2.0 SSOT
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db_timed
from app.modules.auth.services import get_current_user_ctx
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO

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
    request: Request,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms vs ~1200ms ORM)
    db: AsyncSession = Depends(get_db_timed),
) -> Optional[TaxProfileResponse]:
    """Obtiene el perfil fiscal del usuario."""
    from app.shared.observability.request_telemetry import RequestTelemetry
    
    telemetry = RequestTelemetry.create("profile.tax-profile")
    
    # BD 2.0 SSOT: auth_user_id es el identificador canónico
    auth_uid = ctx.auth_user_id
    
    try:
        # Fase: DB Query (BD 2.0 SSOT: filtrar por auth_user_id)
        with telemetry.measure("db_ms"):
            result = await db.execute(
                select(UserTaxProfile).where(UserTaxProfile.auth_user_id == auth_uid)
            )
            profile = result.scalar_one_or_none()
        
        # Fase: Serialization
        with telemetry.measure("ser_ms"):
            if profile is None:
                response = None
            else:
                response = TaxProfileResponse.model_validate(profile)
        
        telemetry.set_flag("auth_user_id", f"{str(auth_uid)[:8]}...")
        telemetry.set_flag("has_profile", profile is not None)
        telemetry.finalize(request, status_code=200, result="success")
        
        return response
        
    except Exception as e:
        telemetry.finalize(request, status_code=500, result="error")
        logger.exception(
            "query_error op=get_tax_profile auth_user_id=%s error=%s",
            f"{str(auth_uid)[:8]}...", str(e)
        )
        raise


@router.put(
    "/tax-profile",
    response_model=TaxProfileResponse,
    summary="Crear o actualizar perfil fiscal",
    description="Crea o actualiza el perfil fiscal del usuario (upsert).",
)
async def upsert_tax_profile(
    request: Request,
    data: TaxProfileUpsertRequest,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms vs ~1200ms ORM)
    db: AsyncSession = Depends(get_db_timed),
) -> TaxProfileResponse:
    """Crea o actualiza el perfil fiscal."""
    from app.shared.observability.request_telemetry import RequestTelemetry
    
    telemetry = RequestTelemetry.create("profile.tax-profile-upsert")
    
    # BD 2.0 SSOT: auth_user_id es el identificador canónico
    auth_uid = ctx.auth_user_id
    user_id = ctx.user_id  # Legacy FK para JOINs internos
    
    try:
        # Fase: DB Query (lookup por auth_user_id - BD 2.0 SSOT)
        with telemetry.measure("db_lookup_ms"):
            result = await db.execute(
                select(UserTaxProfile).where(UserTaxProfile.auth_user_id == auth_uid)
            )
            profile = result.scalar_one_or_none()
        
        # Capturar si es nuevo ANTES de modificar
        was_new = profile is None
        
        # Fase: Business logic + DB write
        with telemetry.measure("db_write_ms"):
            if was_new:
                # Crear nuevo con ambos IDs (BD 2.0 SSOT + legacy FK)
                profile = UserTaxProfile(
                    auth_user_id=auth_uid,  # BD 2.0 SSOT
                    user_id=user_id,  # Legacy FK para JOINs internos
                    status=TaxProfileStatus.DRAFT.value,
                    use_razon_social=False,
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
        
        # Fase: Serialization
        with telemetry.measure("ser_ms"):
            response = TaxProfileResponse.model_validate(profile)
        
        telemetry.set_flag("auth_user_id", f"{str(auth_uid)[:8]}...")
        telemetry.set_flag("is_new", was_new)  # Corregido: usar was_new, no profile is not None
        telemetry.finalize(request, status_code=200, result="success")
        
        logger.info(
            "Tax profile upserted: auth_user_id=%s is_new=%s rfc=%s status=%s",
            f"{str(auth_uid)[:8]}...", was_new, profile.rfc, profile.status
        )
        
        return response
        
    except Exception as e:
        telemetry.finalize(request, status_code=500, result="error")
        logger.exception(
            "query_error op=upsert_tax_profile auth_user_id=%s error=%s",
            f"{str(auth_uid)[:8]}...", str(e)
        )
        raise


__all__ = ["router"]
