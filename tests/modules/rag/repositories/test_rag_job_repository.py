# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/repositories/test_rag_job_repository.py

Tests para RagJobRepository con validación de persistencia real.

Autor: DoxAI
Fecha: 2025-11-28
"""

import pytest
import asyncio
from uuid import uuid4, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.repositories import rag_job_repository
from app.modules.rag.enums import RagPhase, RagJobPhase
from app.modules.projects.models.project_models import Project
from app.modules.projects.enums import ProjectState, ProjectStatus
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.enums import FileCategory, FileType, InputProcessingStatus, StorageBackend


async def _create_test_project(adb: AsyncSession) -> Project:
    """Helper para crear proyecto de prueba con persistencia real."""
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
    """Helper para crear archivo de entrada de prueba con persistencia real."""
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
async def test_create_rag_job(adb: AsyncSession):
    """Test crear un job RAG."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()

    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )

    assert job.job_id is not None
    assert job.project_id == project.id
    assert job.file_id == input_file.file_id
    assert job.created_by == user_id
    assert job.phase_current == RagPhase.convert
    assert job.status == RagJobPhase.queued
    assert job.started_at is not None
    assert job.created_at is not None


@pytest.mark.asyncio
async def test_get_by_id(adb: AsyncSession):
    """Test obtener job por ID."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()

    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )

    retrieved = await rag_job_repository.get_by_id(adb, job.job_id)

    assert retrieved is not None
    assert retrieved.job_id == job.job_id
    assert retrieved.project_id == project.id


@pytest.mark.asyncio
async def test_get_by_id_not_found(adb: AsyncSession):
    """Test obtener job inexistente."""
    result = await rag_job_repository.get_by_id(adb, uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_update_phase_persists_to_db(adb: AsyncSession):
    """Test actualizar fase de job y verificar persistencia real."""
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

    initial_phase = job.phase_current
    assert initial_phase == RagPhase.convert

    # Guardar snapshot del timestamp inicial para compararlo después
    initial_updated_at = job.updated_at

    # Actualizar fase
    updated = await rag_job_repository.update_phase(
        adb,
        job.job_id,
        RagPhase.ocr,
    )

    assert updated is not None
    assert updated.phase_current == RagPhase.ocr
    # Debe haberse modificado el timestamp en BD (puede ser > o < según timings internos)
    assert updated.updated_at != initial_updated_at

    # Verificar persistencia con nuevo get_by_id
    retrieved = await rag_job_repository.get_by_id(adb, job.job_id)
    assert retrieved is not None
    assert retrieved.phase_current == RagPhase.ocr
    assert retrieved.phase_current != initial_phase


@pytest.mark.asyncio
async def test_update_status(adb: AsyncSession):
    """Test actualizar estado de job."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()

    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )

    updated = await rag_job_repository.update_status(
        adb,
        job.job_id,
        RagJobPhase.running,
    )

    assert updated is not None
    assert updated.status == RagJobPhase.running


@pytest.mark.asyncio
async def test_update_status_completed_sets_completed_at(adb: AsyncSession):
    """Test que al completar un job se establece completed_at."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()

    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )

    assert job.completed_at is None

    updated = await rag_job_repository.update_status(
        adb,
        job.job_id,
        RagJobPhase.completed,
    )

    assert updated is not None
    assert updated.completed_at is not None

    # Verificar persistencia con roundtrip
    retrieved = await rag_job_repository.get_by_id(adb, job.job_id)
    assert retrieved is not None
    assert retrieved.completed_at is not None
    assert retrieved.status == RagJobPhase.completed


@pytest.mark.asyncio
async def test_update_status_failed_sets_failed_at(adb: AsyncSession):
    """Test que al fallar un job se establece failed_at."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()

    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )

    assert job.failed_at is None

    updated = await rag_job_repository.update_status(
        adb,
        job.job_id,
        RagJobPhase.failed,
    )

    assert updated is not None
    assert updated.failed_at is not None


@pytest.mark.asyncio
async def test_update_status_cancelled_sets_cancelled_at(adb: AsyncSession):
    """Test que al cancelar un job se establece cancelled_at."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()

    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )

    assert job.cancelled_at is None

    updated = await rag_job_repository.update_status(
        adb,
        job.job_id,
        RagJobPhase.cancelled,
    )

    assert updated is not None
    assert updated.cancelled_at is not None


@pytest.mark.asyncio
async def test_list_by_project(adb: AsyncSession):
    """Test listar jobs por proyecto."""
    project = await _create_test_project(adb)
    input_file_1 = await _create_test_input_file(adb, project.id)
    input_file_2 = await _create_test_input_file(adb, project.id)
    user_id = uuid4()

    job1 = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file_1.file_id,
        created_by=user_id,
    )

    job2 = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file_2.file_id,
        created_by=user_id,
    )

    jobs = await rag_job_repository.list_by_project(adb, project.id)

    assert len(jobs) == 2
    job_ids = {j.job_id for j in jobs}
    assert job1.job_id in job_ids
    assert job2.job_id in job_ids


@pytest.mark.asyncio
async def test_update_phase_and_status_persists_both(adb: AsyncSession):
    """Test actualizar fase y estado simultáneamente con verificación de persistencia."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    user_id = uuid4()

    job = await rag_job_repository.create(
        adb,
        project_id=project.id,
        file_id=input_file.file_id,
        created_by=user_id,
    )

    updated = await rag_job_repository.update_phase_and_status(
        adb,
        job.job_id,
        RagPhase.embed,
        RagJobPhase.running,
    )

    assert updated is not None
    assert updated.phase_current == RagPhase.embed
    assert updated.status == RagJobPhase.running

    # Verificar persistencia con roundtrip
    retrieved = await rag_job_repository.get_by_id(adb, job.job_id)
    assert retrieved is not None
    assert retrieved.phase_current == RagPhase.embed
    assert retrieved.status == RagJobPhase.running
