# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/password_reset_email_retry_service.py

Servicio de reintentos automáticos para correos de password reset fallidos.

Busca registros en password_resets con reset_email_status='failed' o 'pending' stale,
y reintenta el envío respetando límites de intentos y backoff.

Autor: Ixchel Beristain
Fecha: 2025-12-15
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.integrations.email_sender import EmailSender, IEmailSender

logger = logging.getLogger(__name__)


@dataclass
class PasswordResetRetryCandidate:
    """Candidato para reintento de correo de password reset."""
    password_reset_id: int
    user_id: int
    user_email: str
    user_full_name: str
    token: str
    attempts: int
    last_error: Optional[str]
    expires_at: datetime


@dataclass
class PasswordResetRetryResult:
    """Resultado de una ronda de reintentos."""
    processed: int
    sent: int
    failed: int
    skipped: int


class PasswordResetEmailRetryService:
    """
    Servicio para reintentar correos de password reset fallidos.
    
    Diseñado para ser llamado por:
    - Endpoint admin interno (POST /_internal/auth/retry-password-reset-emails)
    - Job pg_cron cada N minutos
    """

    DEFAULT_BATCH_SIZE = 10
    DEFAULT_MAX_ATTEMPTS = 5
    STALE_TTL_MINUTES = 15

    def __init__(
        self,
        db: AsyncSession,
        email_sender: IEmailSender,
    ) -> None:
        self.db = db
        self.email_sender = email_sender

    async def get_retry_candidates(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> List[PasswordResetRetryCandidate]:
        """
        Obtiene candidatos para reintento.
        
        Criterios:
        - reset_email_status = 'failed' AND attempts < max_attempts AND expires_at > now()
        - reset_email_status = 'pending' AND claimed_at stale (> STALE_TTL_MINUTES) AND expires_at > now()
        
        Ordenado por attempts ASC (prioriza los que han fallado menos).
        """
        stmt = text("""
            SELECT 
                pr.id AS password_reset_id,
                pr.user_id,
                u.user_email,
                u.user_full_name,
                pr.token,
                pr.reset_email_attempts,
                pr.reset_email_last_error,
                pr.expires_at
            FROM public.password_resets pr
            JOIN public.app_users u ON u.user_id = pr.user_id
            WHERE 
                pr.expires_at > now()
                AND (
                    (pr.reset_email_status = 'failed' AND pr.reset_email_attempts < :max_attempts)
                    OR (
                        pr.reset_email_status = 'pending' 
                        AND pr.reset_email_claimed_at IS NOT NULL
                        AND pr.reset_email_claimed_at < now() - (:stale_ttl * interval '1 minute')
                    )
                )
            ORDER BY pr.reset_email_attempts ASC, pr.created_at DESC
            LIMIT :batch_size
        """)
        
        result = await self.db.execute(
            stmt,
            {
                "max_attempts": max_attempts,
                "stale_ttl": self.STALE_TTL_MINUTES,
                "batch_size": batch_size,
            },
        )
        
        rows = result.fetchall()
        return [
            PasswordResetRetryCandidate(
                password_reset_id=row[0],
                user_id=row[1],
                user_email=row[2],
                user_full_name=row[3],
                token=row[4],
                attempts=row[5] or 0,
                last_error=row[6],
                expires_at=row[7],
            )
            for row in rows
        ]

    async def retry_batch(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> PasswordResetRetryResult:
        """
        Ejecuta una ronda de reintentos.
        
        Para cada candidato:
        1. Intenta claim atómico (respeta anti-race)
        2. Si claim exitoso, envía correo
        3. Marca como sent o failed
        
        Returns:
            PasswordResetRetryResult con estadísticas de la ronda
        """
        candidates = await self.get_retry_candidates(batch_size, max_attempts)
        
        result = PasswordResetRetryResult(
            processed=len(candidates),
            sent=0,
            failed=0,
            skipped=0,
        )
        
        if not candidates:
            logger.info("password_reset_email_retry_no_candidates")
            return result
        
        logger.info(
            "password_reset_email_retry_starting batch_size=%d candidates=%d",
            batch_size,
            len(candidates),
        )
        
        for candidate in candidates:
            try:
                outcome = await self._retry_single(candidate)
                if outcome == "sent":
                    result.sent += 1
                elif outcome == "failed":
                    result.failed += 1
                else:  # skipped
                    result.skipped += 1
            except Exception as e:
                logger.error(
                    "password_reset_email_retry_unexpected_error reset_id=%s error=%s",
                    candidate.password_reset_id,
                    e,
                )
                result.failed += 1
        
        logger.info(
            "password_reset_email_retry_completed processed=%d sent=%d failed=%d skipped=%d",
            result.processed,
            result.sent,
            result.failed,
            result.skipped,
        )
        
        return result

    async def _claim_for_retry(
        self,
        password_reset_id: int,
    ) -> tuple[bool, int]:
        """
        Claim atómico para evitar race conditions.
        
        Returns:
            (claimed: bool, attempts: int)
        """
        stmt = text("""
            UPDATE public.password_resets
            SET 
                reset_email_claimed_at = now(),
                reset_email_attempts = COALESCE(reset_email_attempts, 0) + 1,
                reset_email_status = 'pending'
            WHERE id = :reset_id
              AND expires_at > now()
              AND (
                  reset_email_status = 'failed'
                  OR (
                      reset_email_status = 'pending'
                      AND reset_email_claimed_at IS NOT NULL
                      AND reset_email_claimed_at < now() - (:stale_ttl * interval '1 minute')
                  )
              )
            RETURNING reset_email_attempts
        """)
        
        result = await self.db.execute(
            stmt,
            {
                "reset_id": password_reset_id,
                "stale_ttl": self.STALE_TTL_MINUTES,
            },
        )
        
        row = result.fetchone()
        if row:
            return True, row[0]
        return False, 0

    async def _mark_sent(self, password_reset_id: int) -> None:
        """Marca el password reset como enviado."""
        stmt = text("""
            UPDATE public.password_resets
            SET 
                reset_email_status = 'sent',
                reset_email_sent_at = now(),
                reset_email_claimed_at = NULL
            WHERE id = :reset_id
        """)
        await self.db.execute(stmt, {"reset_id": password_reset_id})

    async def _mark_failed(self, password_reset_id: int, error_msg: str) -> None:
        """Marca el password reset como fallido."""
        stmt = text("""
            UPDATE public.password_resets
            SET 
                reset_email_status = 'failed',
                reset_email_last_error = :error_msg,
                reset_email_claimed_at = NULL
            WHERE id = :reset_id
        """)
        await self.db.execute(
            stmt,
            {"reset_id": password_reset_id, "error_msg": error_msg[:500]},
        )

    async def _retry_single(
        self,
        candidate: PasswordResetRetryCandidate,
    ) -> str:
        """
        Reintenta envío para un candidato individual.
        
        Returns:
            "sent" | "failed" | "skipped"
        """
        email_masked = candidate.user_email[:3] + "***"
        
        # 1) Claim atómico (respeta anti-race)
        claimed, attempts = await self._claim_for_retry(candidate.password_reset_id)
        
        if not claimed:
            logger.debug(
                "password_reset_email_retry_skipped reset_id=%s (already claimed or expired)",
                candidate.password_reset_id,
            )
            return "skipped"
        
        logger.info(
            "password_reset_email_retry_claimed reset_id=%s email=%s attempt=%d",
            candidate.password_reset_id,
            email_masked,
            attempts,
        )
        
        # 2) Enviar correo usando el contrato real de IEmailSender
        try:
            await self.email_sender.send_password_reset_email(
                to_email=candidate.user_email,
                full_name=candidate.user_full_name or "Usuario",
                reset_token=candidate.token,
            )
            
            # 3) Marcar como enviado
            await self._mark_sent(candidate.password_reset_id)
            await self.db.commit()
            
            logger.info(
                "password_reset_email_retry_sent reset_id=%s email=%s attempt=%d",
                candidate.password_reset_id,
                email_masked,
                attempts,
            )
            
            return "sent"
            
        except Exception as e:
            # Rollback y marcar como failed
            await self.db.rollback()
            
            error_msg = str(e)[:500]
            
            try:
                await self._mark_failed(candidate.password_reset_id, error_msg)
                await self.db.commit()
            except Exception as mark_error:
                logger.error(
                    "password_reset_email_retry_mark_failed_error reset_id=%s error=%s",
                    candidate.password_reset_id,
                    mark_error,
                )
                await self.db.rollback()
            
            logger.error(
                "password_reset_email_retry_failed reset_id=%s email=%s error=%s attempt=%d",
                candidate.password_reset_id,
                email_masked,
                error_msg,
                attempts,
            )
            
            return "failed"


__all__ = ["PasswordResetEmailRetryService", "PasswordResetRetryResult"]

# Fin del archivo
