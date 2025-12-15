# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/welcome_email_retry_service.py

Servicio de reintentos automáticos para welcome emails fallidos.

Busca usuarios con welcome_email_status='failed' o 'pending' stale,
y reintenta el envío respetando límites de intentos y backoff.

Autor: Ixchel Beristain
Fecha: 2025-12-14
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repositories import UserRepository
from app.modules.auth.utils.email_helpers import send_welcome_email_safely
from app.modules.auth.utils.error_classifier import classify_email_error
from app.modules.auth.metrics.collectors.welcome_email_collectors import (
    welcome_email_retry_total,
    welcome_email_sent_total,
    welcome_email_failed_total,
    welcome_email_claimed_total,
)
from app.shared.integrations.email_sender import EmailSender

logger = logging.getLogger(__name__)


@dataclass
class RetryCandidate:
    """Candidato para reintento de welcome email."""
    user_id: int
    user_email: str
    user_full_name: str
    attempts: int
    last_error: Optional[str]


@dataclass
class RetryResult:
    """Resultado de una ronda de reintentos."""
    processed: int
    sent: int
    failed: int
    skipped: int


class WelcomeEmailRetryService:
    """
    Servicio para reintentar welcome emails fallidos.
    
    Diseñado para ser llamado por:
    - Endpoint admin interno (POST /_internal/auth/retry-welcome-emails)
    - Job pg_cron cada N minutos
    """

    DEFAULT_BATCH_SIZE = 10
    DEFAULT_MAX_ATTEMPTS = 5
    STALE_TTL_MINUTES = 15

    def __init__(
        self,
        db: AsyncSession,
        email_sender: EmailSender,
    ) -> None:
        self.db = db
        self.email_sender = email_sender
        self.user_repo = UserRepository(db)

    async def get_retry_candidates(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> List[RetryCandidate]:
        """
        Obtiene candidatos para reintento.
        
        Criterios:
        - welcome_email_status = 'failed' AND attempts < max_attempts
        - welcome_email_status = 'pending' AND claimed_at stale (> STALE_TTL_MINUTES)
        
        Ordenado por attempts ASC (prioriza los que han fallado menos).
        """
        stmt = text("""
            SELECT user_id, user_email, user_full_name, 
                   welcome_email_attempts, welcome_email_last_error
            FROM public.app_users
            WHERE (
                (welcome_email_status = 'failed' AND welcome_email_attempts < :max_attempts)
                OR (
                    welcome_email_status = 'pending' 
                    AND welcome_email_claimed_at < now() - (:stale_ttl * interval '1 minute')
                )
            )
            ORDER BY welcome_email_attempts ASC
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
            RetryCandidate(
                user_id=row[0],
                user_email=row[1],
                user_full_name=row[2],
                attempts=row[3] or 0,
                last_error=row[4],
            )
            for row in rows
        ]

    async def retry_batch(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        credits_assigned: int = 5,  # Default welcome credits
    ) -> RetryResult:
        """
        Ejecuta una ronda de reintentos.
        
        Para cada candidato:
        1. Intenta claim atómico (respeta anti-race)
        2. Si claim exitoso, envía correo
        3. Marca como sent o failed
        4. Actualiza métricas
        
        Returns:
            RetryResult con estadísticas de la ronda
        """
        candidates = await self.get_retry_candidates(batch_size, max_attempts)
        
        result = RetryResult(
            processed=len(candidates),
            sent=0,
            failed=0,
            skipped=0,
        )
        
        if not candidates:
            logger.info("welcome_email_retry_no_candidates")
            return result
        
        logger.info(
            "welcome_email_retry_starting batch_size=%d candidates=%d",
            batch_size,
            len(candidates),
        )
        
        for candidate in candidates:
            try:
                outcome = await self._retry_single(candidate, credits_assigned)
                if outcome == "sent":
                    result.sent += 1
                elif outcome == "failed":
                    result.failed += 1
                else:  # skipped
                    result.skipped += 1
            except Exception as e:
                logger.error(
                    "welcome_email_retry_unexpected_error user_id=%s error=%s",
                    candidate.user_id,
                    e,
                )
                result.failed += 1
                welcome_email_retry_total.labels(outcome="failed").inc()
        
        logger.info(
            "welcome_email_retry_completed processed=%d sent=%d failed=%d skipped=%d",
            result.processed,
            result.sent,
            result.failed,
            result.skipped,
        )
        
        return result

    async def _retry_single(
        self,
        candidate: RetryCandidate,
        credits_assigned: int,
    ) -> str:
        """
        Reintenta envío para un candidato individual.
        
        Returns:
            "sent" | "failed" | "skipped"
        """
        email_masked = candidate.user_email[:3] + "***"
        
        # 1) Claim atómico (respeta anti-race)
        claimed, attempts = await self.user_repo.claim_welcome_email_if_pending(
            user_id=candidate.user_id,
            stale_ttl_minutes=self.STALE_TTL_MINUTES,
        )
        
        if not claimed:
            # Otro proceso ganó la carrera o ya se envió
            logger.debug(
                "welcome_email_retry_skipped user_id=%s (already claimed)",
                candidate.user_id,
            )
            welcome_email_retry_total.labels(outcome="skipped").inc()
            return "skipped"
        
        # Métricas: claim exitoso
        welcome_email_claimed_total.inc()
        
        logger.info(
            "welcome_email_retry_claimed user_id=%s email=%s attempt=%d",
            candidate.user_id,
            email_masked,
            attempts,
        )
        
        # 2) Enviar correo
        try:
            await send_welcome_email_safely(
                self.email_sender,
                email=candidate.user_email,
                full_name=candidate.user_full_name,
                credits_assigned=credits_assigned,
            )
            
            # 3) Marcar como enviado
            await self.user_repo.mark_welcome_email_sent(candidate.user_id)
            await self.db.commit()
            
            # Métricas
            welcome_email_sent_total.labels(provider="smtp").inc()
            welcome_email_retry_total.labels(outcome="sent").inc()
            
            logger.info(
                "welcome_email_retry_sent user_id=%s email=%s attempt=%d",
                candidate.user_id,
                email_masked,
                attempts,
            )
            
            return "sent"
            
        except Exception as e:
            # Rollback y marcar como failed
            await self.db.rollback()
            
            error_msg = str(e)[:500]
            reason = classify_email_error(e)
            
            try:
                await self.user_repo.mark_welcome_email_failed(
                    candidate.user_id,
                    error_msg,
                )
                await self.db.commit()
            except Exception as mark_error:
                logger.error(
                    "welcome_email_retry_mark_failed_error user_id=%s error=%s",
                    candidate.user_id,
                    mark_error,
                )
                await self.db.rollback()
            
            # Métricas
            welcome_email_failed_total.labels(provider="smtp", reason=reason).inc()
            welcome_email_retry_total.labels(outcome="failed").inc()
            
            logger.error(
                "welcome_email_retry_failed user_id=%s email=%s error=%s attempt=%d",
                candidate.user_id,
                email_masked,
                error_msg,
                attempts,
            )
            
            return "failed"


__all__ = ["WelcomeEmailRetryService", "RetryResult"]

# Fin del archivo
