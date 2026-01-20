# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/repositories/rag_job_repository.py

Repositorio async para jobs de indexación RAG.

Responsabilidades:
- CRUD básico sobre RagJob
- Listados por proyecto y usuario
- Actualización de estados y fases
- Consultas de progreso

Autor: DoxAI
Fecha: 2025-11-28
"""

from __future__ import annotations

from typing import Optional, Sequence
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.models.job_models import RagJob
from app.modules.rag.enums import RagJobPhase, RagPhase


class RagJobRepository:
    """
    Repositorio para gestión de jobs RAG.
    
    Responsabilidades:
    - CRUD básico sobre RagJob
    - Listados por proyecto
    - Actualización de estados y fases
    """
    
    async def create(
        self,
        session: AsyncSession,
        *,
        project_id: UUID,
        file_id: UUID,
        status: RagJobPhase = RagJobPhase.queued,
        phase_current: RagPhase = RagPhase.convert,
        needs_ocr: bool = False,
    ) -> RagJob:
        """
        Crea un nuevo job RAG.
        
        Args:
            session: Sesión async de SQLAlchemy
            project_id: ID del proyecto
            file_id: ID del archivo a procesar
            status: Estado inicial del job (queued, running, etc.)
            phase_current: Fase RAG inicial (convert, ocr, etc.)
            
        Returns:
            Instancia de RagJob creada
        """
        now = datetime.now(timezone.utc)
        job = RagJob(
            project_id=project_id,
            file_id=file_id,
            status=status,
            phase_current=phase_current,
            needs_ocr=needs_ocr,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        await session.flush()
        await session.refresh(job)
        return job

    async def get_by_id(
        self,
        session: AsyncSession,
        job_id: UUID,
    ) -> Optional[RagJob]:
        """
        Obtiene un job RAG por su ID.
        
        Args:
            session: Sesión async de SQLAlchemy
            job_id: ID del job
            
        Returns:
            Instancia de RagJob o None si no existe
        """
        stmt = select(RagJob).where(RagJob.job_id == job_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_project(
        self,
        session: AsyncSession,
        project_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[RagJob]:
        """
        Lista jobs RAG de un proyecto.
        
        Args:
            session: Sesión async de SQLAlchemy
            project_id: ID del proyecto
            limit: Máximo de resultados
            offset: Offset para paginación
            
        Returns:
            Secuencia de RagJob
        """
        stmt = (
            select(RagJob)
            .where(RagJob.project_id == project_id)
            .order_by(RagJob.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def update_phase(
        self,
        session: AsyncSession,
        job_id: UUID,
        phase_current: RagPhase,
    ) -> Optional[RagJob]:
        """
        Actualiza la fase RAG actual de un job.
        
        Args:
            session: Sesión async de SQLAlchemy
            job_id: ID del job
            phase_current: Nueva fase del pipeline RAG
            
        Returns:
            Instancia de RagJob actualizada o None si no existe
        """
        job = await self.get_by_id(session, job_id)
        if job is None:
            return None
        
        job.phase_current = phase_current
        job.updated_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(job)
        return job

    async def update_status(
        self,
        session: AsyncSession,
        job_id: UUID,
        status: RagJobPhase,
    ) -> Optional[RagJob]:
        """
        Actualiza el estado de un job RAG.
        
        Args:
            session: Sesión async de SQLAlchemy
            job_id: ID del job
            status: Nuevo estado (queued, running, completed, failed, cancelled)
            
        Returns:
            Instancia de RagJob actualizada o None si no existe
        """
        job = await self.get_by_id(session, job_id)
        if job is None:
            return None
        
        job.status = status
        job.updated_at = datetime.now(timezone.utc)
        
        # Marcar timestamp correspondiente según el estado final
        now = datetime.now(timezone.utc)
        if status == RagJobPhase.completed:
            job.completed_at = now
        elif status == RagJobPhase.failed:
            job.failed_at = now
        elif status == RagJobPhase.cancelled:
            job.cancelled_at = now
        
        await session.flush()
        await session.refresh(job)
        
        # Touch project para reflejar cambio de estado RAG
        await self._touch_project(session, job.project_id, f"rag_status_{status.value}")
        
        return job

    async def update_phase_and_status(
        self,
        session: AsyncSession,
        job_id: UUID,
        phase_current: RagPhase,
        status: RagJobPhase,
    ) -> Optional[RagJob]:
        """
        Actualiza fase RAG y estado de un job simultáneamente.
        
        Args:
            session: Sesión async de SQLAlchemy
            job_id: ID del job
            phase_current: Nueva fase del pipeline RAG
            status: Nuevo estado del job
            
        Returns:
            Instancia de RagJob actualizada o None si no existe
        """
        job = await self.get_by_id(session, job_id)
        if job is None:
            return None
        
        job.phase_current = phase_current
        job.status = status
        job.updated_at = datetime.now(timezone.utc)
        
        # Marcar timestamp correspondiente según el estado final
        now = datetime.now(timezone.utc)
        if status == RagJobPhase.completed:
            job.completed_at = now
        elif status == RagJobPhase.failed:
            job.failed_at = now
        elif status == RagJobPhase.cancelled:
            job.cancelled_at = now
        
        await session.flush()
        await session.refresh(job)
        
        # Touch project para reflejar cambio de fase/estado RAG
        await self._touch_project(session, job.project_id, f"rag_phase_{phase_current.value}_{status.value}")
        
        return job

    async def _touch_project(
        self,
        session: AsyncSession,
        project_id: UUID,
        reason: str,
    ) -> None:
        """
        Helper interno para actualizar projects.updated_at.
        
        Best-effort: captura excepciones para no interrumpir el flujo RAG,
        pero loguea warning con exc_info para diagnóstico.
        """
        import logging
        _logger = logging.getLogger("rag.touch")
        
        try:
            from app.modules.projects.services import touch_project_updated_at
            await touch_project_updated_at(session, project_id, reason=reason)
        except Exception as e:
            _logger.warning(
                "touch_project_failed: project_id=%s reason=%s error=%s",
                str(project_id)[:8],
                reason,
                str(e),
                exc_info=True,
            )


# Instancia global para compatibilidad con código existente que importa como módulo
rag_job_repository = RagJobRepository()


__all__ = [
    "RagJobRepository",
    "rag_job_repository",
]

# Fin del archivo backend/app/modules/rag/repositories/rag_job_repository.py
