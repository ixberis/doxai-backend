# -*- coding: utf-8 -*-
"""
backend/app/routes/internal_email_routes.py

Endpoint interno de prueba de email (solo desarrollo).

Autor: Ixchel Beristain
Actualizado: 2025-12-13
"""

import os
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.shared.integrations.email_sender import EmailSender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/email", tags=["internal-email"])


class EmailTestRequest(BaseModel):
    """Request para prueba de email."""
    to: EmailStr
    kind: Literal["activation", "reset", "welcome"]


class EmailTestResponse(BaseModel):
    """Response de prueba de email."""
    ok: bool
    message: str


def _is_production() -> bool:
    """Verifica si estamos en producción."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    return env == "production"


@router.post("/test", response_model=EmailTestResponse)
async def test_email(request: EmailTestRequest) -> EmailTestResponse:
    """
    Endpoint de prueba para enviar emails.
    Solo disponible en entornos de desarrollo.
    """
    if _is_production():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Endpoint no disponible en producción",
        )

    try:
        sender = EmailSender.from_env()
        
        if request.kind == "activation":
            await sender.send_activation_email(
                to_email=request.to,
                full_name="Usuario de Prueba",
                activation_token="TEST-TOKEN-123456",
            )
        elif request.kind == "reset":
            await sender.send_password_reset_email(
                to_email=request.to,
                full_name="Usuario de Prueba",
                reset_token="TEST-RESET-789012",
            )
        elif request.kind == "welcome":
            await sender.send_welcome_email(
                to_email=request.to,
                full_name="Usuario de Prueba",
                credits_assigned=100,
            )
        
        email_mode = os.getenv("EMAIL_MODE", "console")
        return EmailTestResponse(
            ok=True,
            message=f"Email de {request.kind} enviado a {request.to} (mode={email_mode})",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en test de email: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al enviar email: {str(e)}",
        )


# Fin del script internal_email_routes.py
