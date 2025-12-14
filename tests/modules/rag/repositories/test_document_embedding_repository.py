# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/repositories/test_document_embedding_repository.py

Tests para DocumentEmbeddingRepository.

Autor: DoxAI
Fecha: 2025-11-28
"""

import pytest
from uuid import uuid4, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.repositories import document_embedding_repository
from app.modules.rag.models.embedding_models import DocumentEmbedding
from app.modules.rag.enums import FileCategory
from app.modules.rag.models.chunk_models import ChunkMetadata
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.enums import (
    FileType,
    IngestSource,
    StorageBackend,
    InputProcessingStatus,
    InputFileClass,
)
from app.modules.projects.models.project_models import Project
from app.modules.projects.enums import ProjectState, ProjectStatus


async def _create_test_project(adb: AsyncSession) -> Project:
    """Helper para crear un Project válido."""
    user_id = uuid4()
    project = Project(
        user_id=user_id,
        user_email=f"test_{user_id}@example.com",
        project_name="Test Project",
        project_slug=f"test-project-{uuid4().hex[:8]}",
        project_description="Test project for RAG tests",
        state=ProjectState.CREATED,
        status=ProjectStatus.IN_PROCESS,
    )
    adb.add(project)
    await adb.flush()
    await adb.refresh(project)
    return project


async def _create_test_input_file(adb: AsyncSession, project_id: UUID) -> InputFile:
    """Helper para crear un InputFile válido que genera automáticamente el files_base."""
    input_file = InputFile(
        project_id=project_id,
        input_file_uploaded_by=uuid4(),
        input_file_original_name="test_file.pdf",
        input_file_display_name="Test File",
        input_file_mime_type="application/pdf",
        input_file_size_bytes=1024,
        input_file_type=FileType.pdf,
        input_file_storage_path=f"test/path/{uuid4()}.pdf",
        input_file_ingest_source=IngestSource.upload,
        input_file_storage_backend=StorageBackend.supabase,
        input_file_status=InputProcessingStatus.uploaded,
    )
    adb.add(input_file)
    await adb.flush()
    await adb.refresh(input_file)
    return input_file


async def _create_test_chunk(adb: AsyncSession, file_id: UUID, chunk_index: int = 0) -> ChunkMetadata:
    """Helper para crear un ChunkMetadata válido asociado a un archivo."""
    chunk = ChunkMetadata(
        file_id=file_id,
        chunk_index=chunk_index,
        chunk_text=f"Chunk {chunk_index}",
        token_count=0,
    )
    adb.add(chunk)
    await adb.flush()
    await adb.refresh(chunk)
    return chunk


@pytest.mark.asyncio
async def test_insert_embeddings(adb: AsyncSession):
    """Test insertar embeddings en batch."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    file_id = input_file.file_id
    chunk = await _create_test_chunk(adb, file_id=file_id, chunk_index=0)

    embeddings = [
        DocumentEmbedding(
            file_id=file_id,
            chunk_id=chunk.chunk_id,
            file_category=FileCategory.input,
            chunk_index=i,
            embedding_vector=[0.1 * i] * 1536,
            embedding_model="text-embedding-ada-002",
            is_active=True,
        )
        for i in range(3)
    ]
    
    created = await document_embedding_repository.insert_embeddings(
        adb,
        embeddings,
    )
    
    assert len(created) == 3
    for emb in created:
        assert emb.embedding_id is not None
        assert emb.file_id == file_id


@pytest.mark.asyncio
async def test_get_by_id(adb: AsyncSession):
    """Test obtener embedding por ID."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    file_id = input_file.file_id
    chunk = await _create_test_chunk(adb, file_id=file_id, chunk_index=0)

    embedding = DocumentEmbedding(
        file_id=file_id,
        chunk_id=chunk.chunk_id,
        file_category=FileCategory.input,
        chunk_index=0,
        embedding_vector=[0.1] * 1536,
        embedding_model="text-embedding-ada-002",
        is_active=True,
    )
    
    created = await document_embedding_repository.insert_embeddings(
        adb,
        [embedding],
    )
    emb_id = created[0].embedding_id
    
    retrieved = await document_embedding_repository.get_by_id(adb, emb_id)
    
    assert retrieved is not None
    assert retrieved.embedding_id == emb_id


@pytest.mark.asyncio
async def test_list_by_file(adb: AsyncSession):
    """Test listar embeddings por archivo."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    file_id = input_file.file_id

    chunks = []
    for i in range(5):
        chunks.append(await _create_test_chunk(adb, file_id=file_id, chunk_index=i))

    embeddings = [
        DocumentEmbedding(
            file_id=file_id,
            chunk_id=chunks[i].chunk_id,
            file_category=FileCategory.input,
            chunk_index=i,
            embedding_vector=[0.1 * i] * 1536,
            embedding_model="text-embedding-ada-002",
            is_active=True,
        )
        for i in range(5)
    ]
    
    await document_embedding_repository.insert_embeddings(adb, embeddings)
    
    result = await document_embedding_repository.list_by_file(
        adb,
        file_id,
        only_active=True,
    )
    
    assert len(result) == 5


@pytest.mark.asyncio
async def test_count_by_file(adb: AsyncSession):
    """Test contar embeddings por archivo."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    file_id = input_file.file_id

    chunks = []
    for i in range(7):
        chunks.append(await _create_test_chunk(adb, file_id=file_id, chunk_index=i))

    embeddings = [
        DocumentEmbedding(
            file_id=file_id,
            chunk_id=chunks[i].chunk_id,
            file_category=FileCategory.input,
            chunk_index=i,
            embedding_vector=[0.1 * i] * 1536,
            embedding_model="text-embedding-ada-002",
            is_active=True,
        )
        for i in range(7)
    ]
    
    await document_embedding_repository.insert_embeddings(adb, embeddings)
    
    count = await document_embedding_repository.count_by_file(
        adb,
        file_id,
        only_active=True,
    )
    
    assert count == 7


@pytest.mark.asyncio
async def test_exists_for_file_and_chunk(adb: AsyncSession):
    """Test verificar existencia de embedding para idempotencia."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    file_id = input_file.file_id
    chunk = await _create_test_chunk(adb, file_id=file_id, chunk_index=0)
    model = "text-embedding-ada-002"

    embedding = DocumentEmbedding(
        file_id=file_id,
        chunk_id=chunk.chunk_id,
        file_category=FileCategory.input,
        chunk_index=0,
        embedding_vector=[0.1] * 1536,
        embedding_model=model,
        is_active=True,
    )
    
    await document_embedding_repository.insert_embeddings(adb, [embedding])
    
    exists = await document_embedding_repository.exists_for_file_and_chunk(
        adb,
        file_id=file_id,
        chunk_index=0,
        embedding_model=model,
    )
    
    assert exists is True
    
    # Verificar que no existe para otro chunk
    not_exists = await document_embedding_repository.exists_for_file_and_chunk(
        adb,
        file_id=file_id,
        chunk_index=99,
        embedding_model=model,
    )
    
    assert not_exists is False


@pytest.mark.asyncio
async def test_mark_inactive(adb: AsyncSession):
    """Test marcar embeddings como inactivos."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    file_id = input_file.file_id

    chunks = []
    for i in range(3):
        chunks.append(await _create_test_chunk(adb, file_id=file_id, chunk_index=i))

    embeddings = [
        DocumentEmbedding(
            file_id=file_id,
            chunk_id=chunks[i].chunk_id,
            file_category=FileCategory.input,
            chunk_index=i,
            embedding_vector=[0.1 * i] * 1536,
            embedding_model="text-embedding-ada-002",
            is_active=True,
        )
        for i in range(3)
    ]
    
    await document_embedding_repository.insert_embeddings(adb, embeddings)
    
    count = await document_embedding_repository.mark_inactive(adb, file_id)
    
    assert count == 3
    
    # Verificar que ya no están activos
    active_count = await document_embedding_repository.count_by_file(
        adb,
        file_id,
        only_active=True,
    )
    
    assert active_count == 0


@pytest.mark.asyncio
async def test_insert_embeddings_persists_to_db_with_roundtrip(adb: AsyncSession):
    """Test insertar embeddings y verificar persistencia real con commit y nuevo query."""
    project = await _create_test_project(adb)
    input_file = await _create_test_input_file(adb, project.id)
    file_id = input_file.file_id

    chunks = []
    for i in range(3):
        chunks.append(await _create_test_chunk(adb, file_id=file_id, chunk_index=i))

    embeddings = [
        DocumentEmbedding(
            file_id=file_id,
            chunk_id=chunks[i].chunk_id,
            file_category=FileCategory.input,
            chunk_index=i,
            embedding_vector=[0.2 * i] * 1536,
            embedding_model="text-embedding-ada-002",
            is_active=True,
        )
        for i in range(3)
    ]
    
    # Insertar embeddings (la transacción la maneja el fixture adb)
    created = await document_embedding_repository.insert_embeddings(adb, embeddings)
    
    assert len(created) == 3
    
    # Verificar persistencia con nuevo list_by_file (roundtrip dentro de la misma transacción)
    retrieved = await document_embedding_repository.list_by_file(
        adb,
        file_id,
        only_active=True,
    )
    
    assert len(retrieved) == 3
    for i, emb in enumerate(retrieved):
        assert emb.chunk_index == i
        assert emb.is_active is True
        assert emb.embedding_id is not None
