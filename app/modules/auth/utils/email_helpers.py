
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/utils/email_helpers.py

Helpers de alto nivel para envío de correos relacionados con Auth
(activación, bienvenida, restablecimiento de contraseña).

Autor: Ixchel Beristain
Fecha: 19/11/2025
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status

from app.shared.integrations.email_sender import EmailSender


async def send_activation_email_or_raise(
    email_sender: EmailSender,
    *,
    email: str,
    full_name: Optional[str],
    token: str,
) -> None:
    """
    Envía correo de activación y lanza HTTPException si falla.
    """
    try:
        await email_sender.send_activation_email(
            to_email=email,
            full_name=full_name or "",
            activation_token=token,
        )
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - protección extra
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No fue posible enviar el correo de activación: {e}",
        )


async def send_welcome_email_safely(
    email_sender: EmailSender,
    *,
    email: str,
    full_name: Optional[str],
    credits_assigned: int,
) -> None:
    """
    Envía correo de bienvenida. No lanza excepción hacia arriba,
    solo ignora el error (el caller puede hacer logging si lo requiere).
    """
    try:
        await email_sender.send_welcome_email(
            to_email=email,
            full_name=full_name or "",
            credits_assigned=credits_assigned,
        )
    except Exception:
        return


async def send_password_reset_email_or_raise(
    email_sender: EmailSender,
    *,
    email: str,
    full_name: Optional[str],
    reset_token: str,
) -> None:
    """
    Envía correo de restablecimiento y lanza HTTPException si falla.
    """
    try:
        await email_sender.send_password_reset_email(
            to_email=email,
            full_name=full_name or "",
            reset_token=reset_token,
        )
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No fue posible enviar el correo de restablecimiento: {e}",
        )


__all__ = [
    "send_activation_email_or_raise",
    "send_welcome_email_safely",
    "send_password_reset_email_or_raise",
]

# Fin del script backend/app/modules/auth/utils/email_helpers.py
