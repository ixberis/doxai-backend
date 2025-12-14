# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/services/indexing_service.py

Servicio para gestión de jobs de indexación RAG.

Este servicio orquesta el proceso de indexación de documentos,
incluyendo chunking y generación de embeddings.

REFACTORIZADO v2: Usa repositories en lugar de queries directas.

Autor: DoxAI
Fecha: 2025-10-18 (actualizado 2025-11-28)
"""

import logging
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.schemas.indexing_schemas import (
    IndexingJobCreate,
    IndexingJobResponse,
    JobProgressResponse,
)
from app.modules.rag.enums import RagJobPhase
from app.modules.rag.repositories import rag_job_repository, rag_job_event_repository
from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState

logger = logging.getLogger(__name__)


class IndexingService:
    """
    Servicio para gestión de jobs de indexación.
    
    Responsabilidades:
    - Crear y registrar jobs de indexación
    - Obtener progreso de jobs
    - Validar estados de jobs
    
    v2: Usa rag_job_repository y rag_job_event_repository.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_indexing_job(
        self, 
        data: IndexingJobCreate
    ) -> IndexingJobResponse:
        """
        Crea un nuevo job de indexación.
        
        Args:
            data: Datos del job a crear
            
        Returns:
            IndexingJobResponse con información del job creado
            
        Raises:
            HTTPException: Si el proyecto no existe o está archivado
        """
        # Validar que el proyecto existe
        project = await self.db.get(Project, data.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        
        if project.state == ProjectState.archived:
            raise HTTPException(
                status_code=400, 
                detail="No se puede indexar un proyecto archivado"
            )
        
        logger.info(
            f"Creating indexing job: project={data.project_id}, "
            f"file_id={data.file_id}, user={data.user_id}"
        )
        
        # Crear job usando repository
        job = await rag_job_repository.create(
            self.db,
            project_id=data.project_id,
            file_id=data.file_id,
            created_by=data.user_id,
            status=RagJobPhase.queued,
        )
        
        # Registrar evento inicial
        await rag_job_event_repository.log_event(
            self.db,
            job_id=job.job_id,
            event_type="job_queued",
            message="Job de indexación creado",
        )
        
        return IndexingJobResponse(
            job_id=job.job_id,
            project_id=job.project_id,
            started_by=job.created_by,
            phase=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
    
    async def get_job_progress(
        self, 
        job_id: UUID
    ) -> JobProgressResponse:
        """
        Obtiene el progreso de un job de indexación.
        
        Args:
            job_id: ID del job
            
        Returns:
            JobProgressResponse con estado actual del job y timeline
            
        Raises:
            HTTPException: Si el job no existe
        """
        logger.info(f"Getting progress for job: {job_id}")
        
        # Obtener job usando repository
        job = await rag_job_repository.get_by_id(self.db, job_id)
        if job is None:
            raise HTTPException(
                status_code=404, 
                detail=f"Job {job_id} no encontrado"
            )
        
        # Obtener timeline de eventos y convertir a JobProgressEvent
        raw_timeline = await rag_job_event_repository.get_timeline(
            self.db, 
            job_id
        )
        
        from app.modules.rag.schemas.indexing_schemas import JobProgressEvent
        timeline = []
        for event in raw_timeline:
            # Parsear rag_phase si es string
            phase = event.rag_phase
            if isinstance(phase, str):
                try:
                    from app.modules.rag.enums import RagPhase
                    phase = RagPhase(phase)
                except (ValueError, AttributeError):
                    phase = None
            
            if phase:
                timeline.append(JobProgressEvent(
                    phase=phase,
                    message=event.message,
                    progress_pct=event.progress_pct,
                    created_at=event.created_at,
                ))
            else:
                # FASE 3 - Issue #20: Log warning cuando phase no se puede parsear
                logger.warning(
                    "[get_job_progress] Skipping event with unparseable phase",
                    extra={
                        "job_id": str(job_id),
                        "event_rag_phase": event.rag_phase,
                        "event_type": event.event_type,
                    },
                )
        
        return JobProgressResponse(
            job_id=job.job_id,
            project_id=job.project_id,
            file_id=job.file_id,
            phase=job.phase_current,
            status=job.status,
            progress_pct=self._calculate_progress(job.phase_current),
            started_at=job.started_at,
            finished_at=job.completed_at,
            updated_at=job.updated_at,
            event_count=len(raw_timeline),
            timeline=timeline,
        )
    
    async def list_project_jobs(
        self, 
        project_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[JobProgressResponse]:
        """
        Lista jobs de indexación de un proyecto.
        
        Args:
            project_id: ID del proyecto
            limit: Límite de resultados
            offset: Offset para paginación
            
        Returns:
            Lista de JobProgressResponse
        """
        # Validar que el proyecto existe
        project = await self.db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Proyecto no encontrado")
        
        logger.info(f"Listing jobs for project: {project_id}")
        
        # Obtener jobs usando repository
        jobs = await rag_job_repository.list_by_project(
            self.db,
            project_id,
            limit=limit,
            offset=offset,
        )
        
        return [
            JobProgressResponse(
                job_id=job.job_id,
                project_id=job.project_id,
                file_id=job.file_id,
                phase=job.phase_current,
                status=job.status,
                progress_pct=self._calculate_progress(job.phase_current),
                started_at=job.started_at,
                finished_at=job.completed_at,
                updated_at=job.updated_at,
            )
            for job in jobs
        ]
    
    def _calculate_progress(self, phase: RagJobPhase) -> int:
        """
        Calcula porcentaje de progreso basado en la fase actual del job.
        
        Args:
            phase: Fase actual del job (RagJobPhase: queued, running, completed, etc.)
            
        Returns:
            Porcentaje de progreso (0-100)
            
        Nota:
            Los valores se mapean según el estado del job, no la fase del pipeline.
            Para progreso granular por fase pipeline, usar job.phase_current.
        """
        from app.modules.rag.enums import RagPhase
        
        # Mapa de progreso por fase del pipeline RAG
        pipeline_progress_map = {
            RagPhase.convert: 15,
            RagPhase.ocr: 35,
            RagPhase.chunk: 55,
            RagPhase.embed: 75,
            RagPhase.integrate: 90,
            RagPhase.ready: 100,
        }
        
        # Si phase ya es un RagPhase enum, usar directamente
        if isinstance(phase, RagPhase):
            return pipeline_progress_map.get(phase, 0)
        
        # Si phase es un string, intentar convertir a RagPhase
        if isinstance(phase, str):
            try:
                phase_enum = RagPhase(phase)
                return pipeline_progress_map.get(phase_enum, 0)
            except (ValueError, AttributeError):
                pass
        
        # Si phase es un RagJobPhase (status), mapear a progreso general
        status_progress_map = {
            RagJobPhase.queued: 0,
            RagJobPhase.running: 50,
            RagJobPhase.completed: 100,
            RagJobPhase.failed: 0,
            RagJobPhase.cancelled: 0,
        }
        return status_progress_map.get(phase, 0)
