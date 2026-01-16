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

HOTFIX 2026-01-13:
- Persistencia garantizada con flush/commit/refresh/verificación
- Logs estructurados para trazabilidad
- Manejo explícito de errores de constraint

Autor: DoxAI
Fecha: 2025-12-31
Actualizado: 2026-01-13 - Persistencia garantizada
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db_timed
from app.shared.observability.request_telemetry import RequestTelemetry
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
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
    db: AsyncSession = Depends(get_db_timed),
) -> Optional[TaxProfileResponse]:
    """Obtiene el perfil fiscal del usuario."""
    telemetry = RequestTelemetry.create("profile.tax-profile")
    auth_uid = ctx.auth_user_id
    
    try:
        with telemetry.measure("db_ms"):
            result = await db.execute(
                select(UserTaxProfile).where(UserTaxProfile.auth_user_id == auth_uid)
            )
            profile = result.scalar_one_or_none()
        
        with telemetry.measure("ser_ms"):
            response = TaxProfileResponse.model_validate(profile) if profile else None
        
        telemetry.set_flag("auth_user_id", f"{str(auth_uid)[:8]}...")
        telemetry.set_flag("has_profile", profile is not None)
        telemetry.finalize(request, status_code=200, result="success")
        
        return response
        
    except Exception as e:
        telemetry.finalize(request, status_code=500, result="error")
        logger.exception("query_error op=get_tax_profile auth_user_id=%s", f"{str(auth_uid)[:8]}...")
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
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
    db: AsyncSession = Depends(get_db_timed),
) -> TaxProfileResponse:
    """Crea o actualiza el perfil fiscal con persistencia garantizada."""
    telemetry = RequestTelemetry.create("profile.tax-profile-upsert")
    
    auth_uid = ctx.auth_user_id
    auth_uid_str = str(auth_uid)
    user_id = ctx.user_id
    
    logger.info(
        "tax_profile_upsert_attempt: auth_user_id=%s user_id=%s",
        f"{auth_uid_str[:8]}...", user_id,
    )
    
    try:
        # PASO 1: Lookup por auth_user_id (BD 2.0 SSOT)
        with telemetry.measure("db_lookup_ms"):
            result = await db.execute(
                select(UserTaxProfile).where(UserTaxProfile.auth_user_id == auth_uid)
            )
            profile = result.scalar_one_or_none()
        
        was_new = profile is None
        
        logger.info(
            "tax_profile_lookup: auth_user_id=%s found=%s",
            f"{auth_uid_str[:8]}...", not was_new,
        )
        
        # PASO 2: INSERT o UPDATE
        with telemetry.measure("db_write_ms"):
            if was_new:
                profile = UserTaxProfile(
                    auth_user_id=auth_uid,
                    user_id=user_id,
                    status=TaxProfileStatus.DRAFT.value,
                    use_razon_social=False,
                )
                db.add(profile)
                logger.info(
                    "tax_profile_insert_executed: auth_user_id=%s user_id=%s",
                    f"{auth_uid_str[:8]}...", user_id,
                )
            else:
                logger.info(
                    "tax_profile_update_executed: auth_user_id=%s profile_id=%s",
                    f"{auth_uid_str[:8]}...", profile.id,
                )
            
            # Aplicar campos del request
            for field, value in data.model_dump(exclude_unset=True).items():
                setattr(profile, field, value)
            
            # PASO 3: flush + commit + refresh con logs estructurados
            await db.flush()
            logger.info(
                "tax_profile_flush_ok: auth_user_id=%s profile_id=%s",
                f"{auth_uid_str[:8]}...", profile.id,
            )
            
            await db.commit()
            logger.info(
                "tax_profile_commit_ok: auth_user_id=%s profile_id=%s",
                f"{auth_uid_str[:8]}...", profile.id,
            )
            
            await db.refresh(profile)
        
        # PASO 4: Verificación post-commit con raw SQL
        with telemetry.measure("db_verify_ms"):
            verify_result = await db.execute(
                text("SELECT id FROM public.user_tax_profiles WHERE auth_user_id = :auth_uid"),
                {"auth_uid": auth_uid}
            )
            persisted_row = verify_result.fetchone()
            
            if persisted_row:
                logger.info(
                    "tax_profile_verify_ok: auth_user_id=%s persisted_id=%s",
                    f"{auth_uid_str[:8]}...", persisted_row[0],
                )
            
            if not persisted_row:
                logger.error(
                    "tax_profile_verify_failed: auth_user_id=%s reason=row_not_found_after_commit",
                    f"{auth_uid_str[:8]}...",
                )
                raise HTTPException(
                    status_code=500,
                    detail="Error crítico: datos no persistidos. Contacte soporte.",
                )
        
        # PASO 5: Serializar respuesta
        with telemetry.measure("ser_ms"):
            response = TaxProfileResponse.model_validate(profile)
        
        telemetry.set_flag("auth_user_id", f"{auth_uid_str[:8]}...")
        telemetry.set_flag("is_new", was_new)
        telemetry.set_flag("profile_id", profile.id)
        telemetry.finalize(request, status_code=200, result="success")
        
        # Logs explícitos para auditoría (no usar variables dinámicas)
        if was_new:
            logger.info(
                "tax_profile_created: auth_user_id=%s profile_id=%s rfc=%s use_razon_social=%s razon_social=%s",
                f"{auth_uid_str[:8]}...", profile.id, profile.rfc,
                profile.use_razon_social, profile.razon_social,
            )
        else:
            logger.info(
                "tax_profile_updated: auth_user_id=%s profile_id=%s rfc=%s use_razon_social=%s razon_social=%s",
                f"{auth_uid_str[:8]}...", profile.id, profile.rfc,
                profile.use_razon_social, profile.razon_social,
            )
        
        return response
    
    except HTTPException:
        raise
    
    except (IntegrityError, DBAPIError) as e:
        await db.rollback()
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(
            "tax_profile_upsert_failed: auth_user_id=%s reason=db_error error=%s",
            f"{auth_uid_str[:8]}...", error_msg,
        )
        telemetry.finalize(request, status_code=500, result="error")
        raise HTTPException(status_code=500, detail="Error al guardar perfil fiscal.")
    
    except Exception as e:
        await db.rollback()
        telemetry.finalize(request, status_code=500, result="error")
        logger.exception(
            "tax_profile_upsert_failed: auth_user_id=%s reason=unexpected error=%s",
            f"{auth_uid_str[:8]}...", str(e),
        )
        raise HTTPException(status_code=500, detail="Error inesperado al guardar perfil fiscal.")


__all__ = ["router"]
