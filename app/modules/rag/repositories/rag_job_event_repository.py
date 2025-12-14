# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/repositories/rag_job_event_repository.py

Repositorio async para eventos de jobs RAG.

Responsabilidades:
- Registro de eventos de timeline
- Consulta de timeline por job
- Auditoría de cambios de fase/estado

Autor: DoxAI
Fecha: 2025-11-28
"""

from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.models.job_models import RagJobEvent
from app.modules.rag.enums import RagPhase


class RagJobEventRepository:
    """
    Repositorio para gestión de eventos de jobs RAG.
    
    Responsabilidades:
    - Registro de eventos de timeline
    - Consulta de timeline por job
    - Auditoría de cambios de fase/estado
    """
    
    async def log_event(
        self,
        session: AsyncSession,
        *,
        job_id: UUID,
        event_type: str,
        rag_phase: Optional[RagPhase] = None,
        progress_pct: int = 0,
        message: Optional[str] = None,
        event_payload: Optional[dict] = None,
    ) -> RagJobEvent:
        """
        Registra un evento en la timeline de un job RAG.
        
        Args:
            session: Sesión async de SQLAlchemy
            job_id: ID del job
            event_type: Tipo de evento (job_queued, phase_updated, error, etc.)
            rag_phase: Fase RAG asociada (opcional)
            progress_pct: Porcentaje de progreso
            message: Mensaje descriptivo del evento
            event_payload: Payload dict/JSON del evento (opcional)
            
        Returns:
            Instancia de RagJobEvent creada
        """
        event = RagJobEvent(
            job_id=job_id,
            event_type=event_type,
            rag_phase=rag_phase,
            progress_pct=progress_pct,
            message=message,
            event_payload=event_payload or {},
            created_at=datetime.now(timezone.utc),
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return event

    async def get_timeline(
        self,
        session: AsyncSession,
        job_id: UUID,
        *,
        limit: int = 100,
    ) -> Sequence[RagJobEvent]:
        """
        Obtiene la timeline completa de eventos de un job RAG.
        
        Args:
            session: Sesión async de SQLAlchemy
            job_id: ID del job
            limit: Máximo de eventos a devolver
            
        Returns:
            Secuencia de RagJobEvent ordenados por fecha
        """
        stmt = (
            select(RagJobEvent)
            .where(RagJobEvent.job_id == job_id)
            .order_by(RagJobEvent.created_at.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_latest_event(
        self,
        session: AsyncSession,
        job_id: UUID,
    ) -> Optional[RagJobEvent]:
        """
        Obtiene el evento más reciente de un job RAG.
        
        Args:
            session: Sesión async de SQLAlchemy
            job_id: ID del job
            
        Returns:
            Instancia de RagJobEvent más reciente o None
        """
        stmt = (
            select(RagJobEvent)
            .where(RagJobEvent.job_id == job_id)
            .order_by(RagJobEvent.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


# Instancia global para compatibilidad con código existente que importa como módulo
rag_job_event_repository = RagJobEventRepository()


__all__ = [
    "RagJobEventRepository",
    "rag_job_event_repository",
]

# Fin del archivo backend/app/modules/rag/repositories/rag_job_event_repository.py
