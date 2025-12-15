# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/routes/internal_routes.py

Rutas internas del módulo Auth (no expuestas públicamente).

Incluye:
- Endpoint de retry de welcome emails (para pg_cron/admin)
- Endpoint de retry de password reset emails (para pg_cron/admin)
- Health checks internos

SEGURIDAD: Todos los endpoints (excepto health) requieren service token.

Autor: Ixchel Beristain
Fecha: 2025-12-14
Updated: 2025-12-15 - Añadido endpoint retry-password-reset-emails
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_db
from app.shared.integrations.email_sender import EmailSender
from app.shared.internal_auth import InternalServiceAuth
from app.modules.auth.services.welcome_email_retry_service import (
    WelcomeEmailRetryService,
)
from app.modules.auth.services.password_reset_email_retry_service import (
    PasswordResetEmailRetryService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/_internal/auth",
    tags=["auth-internal"],
)


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
    db: AsyncSession = Depends(get_db),
) -> RetryWelcomeEmailsResponse:
    """
    Ejecuta una ronda de reintentos de welcome emails.
    
    Este endpoint es idempotente y seguro para llamar múltiples veces.
    El claim atómico garantiza que no se envíen correos duplicados.
    """
    try:
        email_sender = EmailSender.from_env()
        service = WelcomeEmailRetryService(db, email_sender)
        
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
        logger.error(f"retry_welcome_emails_error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during retry: {str(e)}",
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
    db: AsyncSession = Depends(get_db),
) -> RetryPasswordResetEmailsResponse:
    """
    Ejecuta una ronda de reintentos de correos de password reset.
    
    Este endpoint es idempotente y seguro para llamar múltiples veces.
    El claim atómico garantiza que no se envíen correos duplicados.
    Solo procesa tokens que no han expirado.
    """
    try:
        email_sender = EmailSender.from_env()
        service = PasswordResetEmailRetryService(db, email_sender)
        
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
        logger.error(f"retry_password_reset_emails_error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during retry: {str(e)}",
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
