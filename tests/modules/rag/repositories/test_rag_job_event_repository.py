# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/repositories/test_rag_job_event_repository.py

Tests para RagJobEventRepository con validación de persistencia.

Autor: DoxAI
Fecha: 2025-11-28
"""

import pytest
from uuid import uuid4, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.repositories import rag_job_repository, rag_job_event_repository
from app.modules.rag.enums import RagPhase, RagJobPhase
from app.modules.projects.models.project_models import Project
from app.modules.projects.enums import ProjectState, ProjectStatus
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.enums import FileCategory, FileType, InputProcessingStatus, StorageBackend


async def _create_test_project(adb: AsyncSession) -> Project:
    """Helper para crear proyecto de prueba."""
    project = Project(
        user_id=uuid4(),
        user_email="test@doxai.com",
        created_by=uuid4(),
        project_name="Test RAG Project",
        project_slug=f"test-rag-{uuid4().hex[:8]}",
        project_description="Project for RAG testing",
        state=ProjectState.READY,
        status=ProjectStatus.IN_PROCESS,
    )
    adb.add(project)
    await adb.flush()
    await adb.refresh(project)
    return project


async def _create_test_input_file(adb: AsyncSession, project_id: UUID) -> InputFile:
    """Helper para crear archivo de entrada de prueba."""
    input_file = InputFile(
        project_id=project_id,
        input_file_uploaded_by=uuid4(),
        input_file_display_name="test_document.pdf",
        input_file_original_name="test_document.pdf",
        input_file_mime_type="application/pdf",
        input_file_size_bytes=1024,
        input_file_type=FileType.document,
        input_file_storage_path=f"test/{uuid4()}.pdf",
        input_file_storage_backend=StorageBackend.supabase,
        input_file_category=FileCategory.input,
        input_file_status=InputProcessingStatus.uploaded,
    )
    adb.add(input_file)
    await adb.flush()
    await adb.refresh(input_file)
    return input_file


@pytest.mark.asyncio
async def test_log_event(adb: AsyncSession):
    """Test registrar evento en timeline."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()
    
    # Crear job primero
    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )
    
    # Registrar evento
    event = await rag_job_event_repository.log_event(
        adb,
        job_id=job.job_id,
        event_type="phase_updated",
        rag_phase=RagPhase.convert,
        message="Iniciando conversión de archivo",
    )
    
    assert event.job_event_id is not None
    assert event.job_id == job.job_id
    assert event.event_type == "phase_updated"
    assert event.rag_phase == RagPhase.convert
    assert event.message == "Iniciando conversión de archivo"
    assert event.created_at is not None


@pytest.mark.asyncio
async def test_get_timeline(adb: AsyncSession):
    """Test obtener timeline completa de un job."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()
    
    # Crear job
    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )
    
    # Registrar varios eventos
    await rag_job_event_repository.log_event(
        adb,
        job_id=job.job_id,
        event_type="job_queued",
        message="Job encolado",
    )
    
    await rag_job_event_repository.log_event(
        adb,
        job_id=job.job_id,
        event_type="phase_updated",
        rag_phase=RagPhase.convert,
        message="Iniciando conversión",
    )
    
    await rag_job_event_repository.log_event(
        adb,
        job_id=job.job_id,
        event_type="phase_updated",
        rag_phase=RagPhase.ocr,
        message="Iniciando OCR",
    )
    
    # Obtener timeline
    timeline = await rag_job_event_repository.get_timeline(
        adb,
        job.job_id,
    )
    
    assert len(timeline) == 3
    assert timeline[0].event_type == "job_queued"
    assert timeline[1].rag_phase == RagPhase.convert
    assert timeline[2].rag_phase == RagPhase.ocr


@pytest.mark.asyncio
async def test_get_latest_event(adb: AsyncSession):
    """Test obtener el evento más reciente de un job."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()
    
    # Crear job
    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )
    
    # Registrar varios eventos
    await rag_job_event_repository.log_event(
        adb,
        job_id=job.job_id,
        event_type="job_queued",
        message="Job encolado",
    )
    
    latest = await rag_job_event_repository.log_event(
        adb,
        job_id=job.job_id,
        event_type="phase_updated",
        rag_phase=RagPhase.ocr,
        message="Fase más reciente",
    )
    
    # Obtener último evento
    retrieved = await rag_job_event_repository.get_latest_event(
        adb,
        job.job_id,
    )
    
    assert retrieved is not None
    assert retrieved.job_event_id == latest.job_event_id
    assert retrieved.event_type == "phase_updated"
    assert retrieved.rag_phase == RagPhase.ocr
