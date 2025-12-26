# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/routes/internal_routes.py

Rutas internas del módulo Auth (no expuestas públicamente).

Incluye:
- Endpoint de retry de welcome emails (para pg_cron/admin)
- Endpoint de retry de password reset emails (para pg_cron/admin)
- Health checks internos
- Endpoint QA para recuperar activation token (solo staging/dev)

SEGURIDAD: Todos los endpoints (excepto health) requieren service token.

Autor: Ixchel Beristain
Fecha: 2025-12-14
Updated: 2025-12-15 - Añadido endpoint retry-password-reset-emails
Updated: 2025-12-26 - Añadido endpoint QA activation-token
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.shared.integrations.email_sender import EmailSender, IEmailSender
from app.shared.internal_auth import InternalServiceAuth
from app.modules.auth.services.welcome_email_retry_service import (
    WelcomeEmailRetryService,
    RetryResult,
)
from app.modules.auth.services.password_reset_email_retry_service import (
    PasswordResetEmailRetryService,
)
from app.modules.auth.models.activation_models import AccountActivation
from app.modules.auth.models.user_models import AppUser
from app.modules.auth.enums import ActivationStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/_internal/auth",
    tags=["auth-internal"],
)


# -----------------------------------------------------------------------------
# Dependency Factories (para DI y testing)
# -----------------------------------------------------------------------------

def get_email_sender() -> IEmailSender:
    """Factory para obtener EmailSender. Override en tests."""
    return EmailSender.from_env()


async def get_welcome_email_retry_service(
    db: AsyncSession = Depends(get_db),
    email_sender: IEmailSender = Depends(get_email_sender),
) -> WelcomeEmailRetryService:
    """Factory para WelcomeEmailRetryService. Override en tests."""
    return WelcomeEmailRetryService(db, email_sender)


async def get_password_reset_email_retry_service(
    db: AsyncSession = Depends(get_db),
    email_sender: IEmailSender = Depends(get_email_sender),
) -> PasswordResetEmailRetryService:
    """Factory para PasswordResetEmailRetryService. Override en tests."""
    return PasswordResetEmailRetryService(db, email_sender)


# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------

class RetryWelcomeEmailsRequest(BaseModel):
    """Request para reintento de welcome emails."""
    batch_size: int = Field(default=10, ge=1, le=100)
    max_attempts: int = Field(default=5, ge=1, le=10)
    credits_assigned: int = Field(default=5, ge=0, le=100)


class RetryWelcomeEmailsResponse(BaseModel):
    """Response del reintento de welcome emails."""
    processed: int
    sent: int
    failed: int
    skipped: int
    message: str


class RetryPasswordResetEmailsRequest(BaseModel):
    """Request para reintento de correos de password reset."""
    batch_size: int = Field(default=10, ge=1, le=100)
    max_attempts: int = Field(default=5, ge=1, le=10)


class RetryPasswordResetEmailsResponse(BaseModel):
    """Response del reintento de correos de password reset."""
    processed: int
    sent: int
    failed: int
    skipped: int
    message: str


# -----------------------------------------------------------------------------
# Endpoints (protegidos con service token)
# -----------------------------------------------------------------------------

@router.post(
    "/retry-welcome-emails",
    response_model=RetryWelcomeEmailsResponse,
    summary="Reintenta welcome emails fallidos",
    description="""
    Endpoint interno para reintento de welcome emails.
    
    **REQUIERE**: Authorization: Bearer <APP_SERVICE_TOKEN>
    
    Diseñado para ser llamado por:
    - pg_cron job (cada 5 minutos)
    - Admin manual vía curl/Postman
    
    **Comportamiento**:
    - Busca usuarios con welcome_email_status='failed' o 'pending' stale
    - Respeta límite de intentos (max_attempts)
    - Usa claim atómico (anti-race condition)
    - Actualiza métricas Prometheus
    """,
    include_in_schema=False,  # No exponer en OpenAPI público
)
async def retry_welcome_emails(
    request: RetryWelcomeEmailsRequest,
    _auth: InternalServiceAuth,  # Requiere service token
    service: WelcomeEmailRetryService = Depends(get_welcome_email_retry_service),
) -> RetryWelcomeEmailsResponse:
    """
    Ejecuta una ronda de reintentos de welcome emails.
    
    Este endpoint es idempotente y seguro para llamar múltiples veces.
    El claim atómico garantiza que no se envíen correos duplicados.
    
    BEST-EFFORT: Nunca devuelve 500 por errores SMTP/SSL.
    Los fallos se registran y reportan en la respuesta.
    """
    try:
        result = await service.retry_batch(
            batch_size=request.batch_size,
            max_attempts=request.max_attempts,
            credits_assigned=request.credits_assigned,
        )
        
        logger.info(
            "retry_welcome_emails_completed processed=%d sent=%d failed=%d skipped=%d",
            result.processed,
            result.sent,
            result.failed,
            result.skipped,
        )
        
        return RetryWelcomeEmailsResponse(
            processed=result.processed,
            sent=result.sent,
            failed=result.failed,
            skipped=result.skipped,
            message=f"Retry completed: {result.sent} sent, {result.failed} failed, {result.skipped} skipped",
        )
        
    except Exception as e:
        # Best-effort: loguear pero NO devolver 500
        logger.error(
            "retry_welcome_emails_batch_error: %s",
            str(e),
            exc_info=True,
        )
        return RetryWelcomeEmailsResponse(
            processed=0,
            sent=0,
            failed=0,
            skipped=0,
            message=f"Batch processing error: {str(e)[:100]}",
        )


@router.post(
    "/retry-password-reset-emails",
    response_model=RetryPasswordResetEmailsResponse,
    summary="Reintenta correos de password reset fallidos",
    description="""
    Endpoint interno para reintento de correos de password reset.
    
    **REQUIERE**: Authorization: Bearer <APP_SERVICE_TOKEN>
    
    Diseñado para ser llamado por:
    - pg_cron job (cada 5 minutos)
    - Admin manual vía curl/Postman
    
    **Comportamiento**:
    - Busca password_resets con reset_email_status='failed' o 'pending' stale
    - Solo procesa tokens NO expirados (expires_at > now())
    - Respeta límite de intentos (max_attempts)
    - Usa claim atómico (anti-race condition)
    """,
    include_in_schema=False,  # No exponer en OpenAPI público
)
async def retry_password_reset_emails(
    request: RetryPasswordResetEmailsRequest,
    _auth: InternalServiceAuth,  # Requiere service token
    service: PasswordResetEmailRetryService = Depends(get_password_reset_email_retry_service),
) -> RetryPasswordResetEmailsResponse:
    """
    Ejecuta una ronda de reintentos de correos de password reset.
    
    Este endpoint es idempotente y seguro para llamar múltiples veces.
    El claim atómico garantiza que no se envíen correos duplicados.
    Solo procesa tokens que no han expirado.
    
    BEST-EFFORT: Nunca devuelve 500 por errores SMTP/SSL.
    """
    try:
        result = await service.retry_batch(
            batch_size=request.batch_size,
            max_attempts=request.max_attempts,
        )
        
        logger.info(
            "retry_password_reset_emails_completed processed=%d sent=%d failed=%d skipped=%d",
            result.processed,
            result.sent,
            result.failed,
            result.skipped,
        )
        
        return RetryPasswordResetEmailsResponse(
            processed=result.processed,
            sent=result.sent,
            failed=result.failed,
            skipped=result.skipped,
            message=f"Retry completed: {result.sent} sent, {result.failed} failed, {result.skipped} skipped",
        )
        
    except Exception as e:
        logger.error(
            "retry_password_reset_emails_batch_error: %s",
            str(e),
            exc_info=True,
        )
        return RetryPasswordResetEmailsResponse(
            processed=0,
            sent=0,
            failed=0,
            skipped=0,
            message=f"Batch processing error: {str(e)[:100]}",
        )


# -----------------------------------------------------------------------------
# QA Endpoint: Obtener activation token (solo staging/dev)
# -----------------------------------------------------------------------------

def _is_qa_endpoints_allowed() -> bool:
    """
    Verifica si los endpoints QA internos están permitidos.
    
    SEGURIDAD: Usa flag explícito ALLOW_INTERNAL_QA_ENDPOINTS=1.
    NO inferimos de ENVIRONMENT para evitar inconsistencias en env vars.
    
    Returns:
        True solo si ALLOW_INTERNAL_QA_ENDPOINTS == "1" o "true"
    """
    flag = os.getenv("ALLOW_INTERNAL_QA_ENDPOINTS", "").lower()
    return flag in ("1", "true")


class ActivationTokenResponse(BaseModel):
    """Response con el token de activación para QA."""
    email: str
    token: str
    expires_at: str
    status: str
    message: str = "Token recuperado para QA. Solo disponible si ALLOW_INTERNAL_QA_ENDPOINTS=1."


@router.get(
    "/activation-token",
    response_model=ActivationTokenResponse,
    summary="Obtener activation token para QA",
    description="""
    **SOLO DISPONIBLE SI ALLOW_INTERNAL_QA_ENDPOINTS=1**
    
    Endpoint de QA para recuperar el token de activación de un usuario
    cuando el correo no se pudo enviar (ej: MailerSend trial limit).
    
    **REQUIERE**: 
    - Env var: ALLOW_INTERNAL_QA_ENDPOINTS=1
    - Authorization: Bearer <APP_SERVICE_TOKEN>
    
    Devuelve 403 si ALLOW_INTERNAL_QA_ENDPOINTS no está habilitado.
    """,
    include_in_schema=False,  # No exponer en OpenAPI público
)
async def get_activation_token_for_qa(
    email: EmailStr = Query(..., description="Email del usuario"),
    _auth: InternalServiceAuth,  # InternalServiceAuth ya incluye Depends()
    db: AsyncSession = Depends(get_db),
) -> ActivationTokenResponse:
    """
    Recupera el token de activación pendiente más reciente para un email.
    
    SOLO disponible si ALLOW_INTERNAL_QA_ENDPOINTS=1.
    Devuelve 403 Forbidden si no está habilitado.
    """
    # GUARD: Flag explícito - NO inferir de ENVIRONMENT
    if not _is_qa_endpoints_allowed():
        logger.warning(
            "activation_token_qa_blocked flag_missing=true email=%s",
            email[:3] + "***",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint QA no habilitado. Requiere ALLOW_INTERNAL_QA_ENDPOINTS=1.",
        )
    
    # Buscar usuario por email
    user_result = await db.execute(
        select(AppUser).where(AppUser.user_email == email.lower())
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario no encontrado: {email}",
        )
    
    # Buscar activation token pendiente más reciente
    # Criterios: status='sent', no consumido, no expirado
    now_utc = datetime.now(timezone.utc)
    
    activation_result = await db.execute(
        select(AccountActivation)
        .where(
            AccountActivation.user_id == user.user_id,
            AccountActivation.status == ActivationStatus.sent,  # Enum real: 'sent'
            AccountActivation.consumed_at.is_(None),
            AccountActivation.expires_at > now_utc,  # Solo tokens válidos
        )
        .order_by(AccountActivation.created_at.desc())
        .limit(1)
    )
    activation = activation_result.scalar_one_or_none()
    
    if not activation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay token de activación pendiente/válido para: {email}. Puede estar expirado o ya consumido.",
        )
    
    logger.info(
        "activation_token_qa_retrieved email=%s user_id=%s token_preview=%s expires_at=%s",
        email[:3] + "***",
        user.user_id,
        activation.token[:8] + "...",
        activation.expires_at.isoformat(),
    )
    
    return ActivationTokenResponse(
        email=email,
        token=activation.token,
        expires_at=activation.expires_at.isoformat(),
        status=activation.status.value,
    )


# -----------------------------------------------------------------------------
# Health check (sin autenticación para uso de load balancers)
# -----------------------------------------------------------------------------

@router.get(
    "/health",
    summary="Health check interno",
    include_in_schema=False,
)
async def internal_health() -> dict:
    """Health check para el módulo auth interno."""
    return {"status": "ok", "module": "auth-internal"}


__all__ = ["router"]

# Fin del archivo
