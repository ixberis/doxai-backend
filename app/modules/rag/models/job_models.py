# -*- coding: utf-8 -*-
"""
backend/app/modules/rag/models/job_models.py

Modelos ORM para gestión de jobs de indexación RAG.

Incluye RagJob (estado y progreso) y RagJobEvent (timeline de eventos).
Usa RagJobPhase para estado del job y RagPhase para fase del pipeline.

Autor: DoxAI
Fecha: 2025-10-28
Actualizado: 2025-11-28 (FASE 3 - Issue #29)
"""

from uuid import uuid4
from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, CheckConstraint,
    ForeignKey, func, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.shared.database.database import Base
from app.modules.rag.enums import RagJobPhase, RagPhase
from app.modules.rag.enums.rag_phase_enum import RagJobPhaseType, RagPhaseType


class RagJob(Base):
    """
    Job de indexación RAG con seguimiento de estado y timeline.
    
    Atributos:
        job_id: Identificador único del job
        project_id: ID del proyecto
        file_id: ID del archivo a procesar
        started_by: ID del usuario que inició el job
        job_phase: Fase actual del job (queued, running, completed, failed, cancelled)
        current_rag_phase: Fase RAG actual (convert, ocr, chunk, embed, etc.)
        progress_pct: Porcentaje de progreso (0-100)
        started_at: Timestamp de inicio
        created_at: Timestamp de creación
        updated_at: Última actualización
        completed_at: Timestamp de finalización exitosa
        failed_at: Timestamp de fallo
        cancelled_at: Timestamp de cancelación
    """
    __tablename__ = "rag_jobs"

    __table_args__ = (
        CheckConstraint(
            "progress_pct >= 0 AND progress_pct <= 100",
            name="check_progress_pct_range"
        ),
    )

    job_id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4,
        comment="Identificador único del job"
    )

    project_id = Column(
        UUID(as_uuid=True), 
        nullable=False,
        comment="ID del proyecto"
    )

    file_id = Column(
        UUID(as_uuid=True), 
        nullable=False,
        comment="ID del archivo a procesar"
    )

    # Nota: Audit trail (created_by) se maneja en rag_job_events,
    # no en la tabla rag_jobs (diseño por eventos/logs).

    status = Column(RagJobPhaseType(), nullable=False)
    phase_current = Column(RagPhaseType(), nullable=True)

    progress_pct = Column(
        Integer,
        CheckConstraint("progress_pct >= 0 AND progress_pct <= 100", name="check_progress_pct_range"),
        nullable=False,
        default=0,
        comment="Porcentaje de progreso (0-100)"
    )

    needs_ocr = Column(
        Boolean,
        nullable=False,
        server_default=func.text("false"),
        comment="Indica si el job requiere OCR explícito"
    )

    # Nota: El campo `message` se gestionará a nivel de eventos (RagJobEvent),
    # no como columna directa en `rag_jobs` para mantener el esquema SQL alineado.

    started_at = Column(
        DateTime,
        nullable=True,
        comment="Timestamp de inicio"
    )

    created_at = Column(
        DateTime, 
        nullable=False, 
        server_default=func.now(),
        comment="Timestamp de creación"
    )

    updated_at = Column(
        DateTime, 
        nullable=False, 
        server_default=func.now(),
        onupdate=func.now(),
        comment="Última actualización"
    )

    completed_at = Column(
        DateTime, 
        nullable=True,
        comment="Timestamp de finalización exitosa"
    )

    failed_at = Column(
        DateTime, 
        nullable=True,
        comment="Timestamp de fallo"
    )

    cancelled_at = Column(
        DateTime, 
        nullable=True,
        comment="Timestamp de cancelación"
    )

    def __repr__(self):
        return f"<RagJob(id={self.job_id}, phase={self.status}, progress={self.progress_pct}%)>"


class RagJobEvent(Base):
    """
    Eventos en el timeline de un job de indexación.
    
    Atributos:
        job_event_id: Identificador único del evento
        job_id: ID del job asociado
        phase: Fase RAG del evento
        status: Estado del evento (running, completed, failed, etc.)
        progress_pct: Porcentaje de progreso en ese momento
        message: Mensaje descriptivo del evento
        created_at: Timestamp del evento
    """
    __tablename__ = "rag_job_events"

    job_event_id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4,
        comment="Identificador único del evento"
    )

    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_jobs.job_id", ondelete="CASCADE"),
        nullable=False,
        comment="ID del job asociado"
    )

    event_type = Column(
        String(100),
        nullable=False,
        comment="Tipo de evento (job_queued, phase_updated, error, etc.)"
    )
    
    rag_phase = Column(
        RagPhaseType(),
        nullable=True,
        comment="Fase RAG asociada al evento"
    )

    progress_pct = Column(
        Integer,
        CheckConstraint("progress_pct >= 0 AND progress_pct <= 100", name="check_event_progress_pct_range"),
        nullable=True,
        default=0,
        comment="Porcentaje de progreso"
    )

    message = Column(
        String(500),
        nullable=True,
        comment="Mensaje descriptivo del evento"
    )
    
    event_payload = Column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Payload JSON del evento"
    )

    created_at = Column(
        DateTime, 
        nullable=False, 
        server_default=func.now(),
        comment="Timestamp del evento"
    )

    def __repr__(self):
        return f"<RagJobEvent(id={self.job_event_id}, job={self.job_id}, event_type={self.event_type})>"
