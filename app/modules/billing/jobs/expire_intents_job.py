# -*- coding: utf-8 -*-
"""
backend/app/modules/billing/jobs/expire_intents_job.py

Job programado para expirar checkout intents viejos.

Autor: DoxAI
Fecha: 2025-12-29
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database.database import get_async_session_context
from app.shared.scheduler import get_scheduler
from app.modules.billing.models import CheckoutIntent, CheckoutIntentStatus

logger = logging.getLogger(__name__)

# ID del job para referencia
EXPIRE_INTENTS_JOB_ID = "billing_expire_checkout_intents"

# TTL por defecto: 60 minutos
DEFAULT_TTL_MINUTES = 60


async def expire_checkout_intents(
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
    session: Optional[AsyncSession] = None,
) -> int:
    """
    Marca como 'expired' todos los intents en estado created/pending
    que superaron el TTL.
    
    Args:
        ttl_minutes: Tiempo de vida en minutos (default 60)
        session: Sesión async opcional (si no se provee, crea una nueva)
        
    Returns:
        Número de intents expirados
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
    
    async def _do_expire(sess: AsyncSession) -> int:
        # Batch update seguro: solo created/pending antes del cutoff
        stmt = (
            update(CheckoutIntent)
            .where(
                and_(
                    CheckoutIntent.status.in_([
                        CheckoutIntentStatus.CREATED.value,
                        CheckoutIntentStatus.PENDING.value,
                    ]),
                    CheckoutIntent.created_at < cutoff_time,
                )
            )
            .values(status=CheckoutIntentStatus.EXPIRED.value)
        )
        
        result = await sess.execute(stmt)
        await sess.commit()
        
        return result.rowcount
    
    if session is not None:
        expired_count = await _do_expire(session)
    else:
        # Crear sesión propia para el job
        async with get_async_session_context() as sess:
            expired_count = await _do_expire(sess)
    
    if expired_count > 0:
        logger.info(
            "Expired %d checkout intents (TTL=%d min, cutoff=%s)",
            expired_count,
            ttl_minutes,
            cutoff_time.isoformat(),
        )
    else:
        logger.debug(
            "No checkout intents to expire (TTL=%d min)",
            ttl_minutes,
        )
    
    return expired_count


def register_expire_intents_job(
    interval_minutes: int = 5,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> str:
    """
    Registra el job de expiración en el scheduler global.
    
    Args:
        interval_minutes: Cada cuántos minutos ejecutar (default 5)
        ttl_minutes: TTL para expirar intents (default 60)
        
    Returns:
        ID del job registrado
    """
    scheduler = get_scheduler()
    
    job_id = scheduler.add_interval_job(
        func=expire_checkout_intents,
        job_id=EXPIRE_INTENTS_JOB_ID,
        minutes=interval_minutes,
        ttl_minutes=ttl_minutes,
    )
    
    logger.info(
        "Registered expire intents job: id=%s interval=%d min ttl=%d min",
        job_id,
        interval_minutes,
        ttl_minutes,
    )
    
    return job_id


__all__ = [
    "expire_checkout_intents",
    "register_expire_intents_job",
    "EXPIRE_INTENTS_JOB_ID",
]
