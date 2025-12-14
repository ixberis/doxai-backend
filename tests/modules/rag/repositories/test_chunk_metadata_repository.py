# -*- coding: utf-8 -*-
"""
backend/tests/modules/rag/repositories/test_chunk_metadata_repository.py

Tests para ChunkMetadataRepository.

Autor: DoxAI
Fecha: 2025-11-28
"""

import pytest
from uuid import uuid4, UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.repositories import chunk_metadata_repository
from app.modules.rag.models.chunk_models import ChunkMetadata
from app.modules.files.models.files_base_models import FilesBase
from app.modules.files.enums import FileType


async def _create_valid_file_id(session: AsyncSession, project_id: UUID | None = None) -> UUID:
    """Helper para crear un file_id válido en toda la cadena Files/Projects.

    Crea:
    - Project mínimo con IDs de usuario sintéticos (UUID)
    - InputFile mínimo asociado al proyecto
    - FilesBase con logical_role = input y FK al InputFile

    De esta forma, todas las FKs (projects, input_files, files_base, chunk_metadata)
    quedan satisfechas y los tests pueden insertar chunks sin violar integridad,
    sin depender del modelo AppUser (que usa PK entero).
    """
    from app.modules.projects.models.project_models import Project
    from app.modules.files.models.input_file_models import InputFile

    # 1) IDs sintéticos de usuario (UUID) compatibles con columnas UUID en projects/input_files
    synthetic_user_id: UUID = uuid4()

    # 2) Proyecto asociado al "usuario" sintético
    if project_id is None:
        project_id = uuid4()

    project = Project(
        id=project_id,
        user_id=synthetic_user_id,
        user_email=f"test_user_{uuid4()}@example.com",
        created_by=synthetic_user_id,
        updated_by=synthetic_user_id,
        project_name="Test Project for ChunkMetadata",
        project_slug=f"test-project-{project_id}",
        project_description=None,
    )
    session.add(project)
    await session.flush()

    # 3) InputFile mínimo para satisfacer FKs de files_base
    input_file = InputFile(
        project_id=project.id,
        input_file_uploaded_by=synthetic_user_id,
        input_file_original_name="test.pdf",
        input_file_display_name="test.pdf",
        input_file_mime_type="application/pdf",
        input_file_extension="pdf",
        input_file_size_bytes=123,
        input_file_type=FileType.document,
        input_file_storage_path="test/path/test.pdf",
    )
    session.add(input_file)
    await session.flush()

    # 4) Recuperar FilesBase creado por el trigger y retornar su file_id
    from sqlalchemy import select

    result = await session.execute(
        select(FilesBase.file_id).where(FilesBase.input_file_id == input_file.input_file_id)
    )
    file_id = result.scalar_one()
    return file_id


@pytest.mark.asyncio
async def test_insert_chunks(adb: AsyncSession):
    """Test insertar chunks en batch."""
    file_id = await _create_valid_file_id(adb)
    
    chunks = [
        ChunkMetadata(
            file_id=file_id,
            chunk_index=i,
            chunk_text=f"Texto del chunk {i}",
            token_count=10,
        )
        for i in range(3)
    ]
    
    created = await chunk_metadata_repository.insert_chunks(adb, chunks)
    
    assert len(created) == 3
    for chunk in created:
        assert chunk.chunk_id is not None
        assert chunk.file_id == file_id


@pytest.mark.asyncio
async def test_get_by_id(adb: AsyncSession):
    """Test obtener chunk por ID."""
    file_id = await _create_valid_file_id(adb)
    
    chunk = ChunkMetadata(
        file_id=file_id,
        chunk_index=0,
        chunk_text="Test content",
        token_count=5,
    )
    
    created = await chunk_metadata_repository.insert_chunks(adb, [chunk])
    chunk_id = created[0].chunk_id
    
    retrieved = await chunk_metadata_repository.get_by_id(adb, chunk_id)
    
    assert retrieved is not None
    assert retrieved.chunk_id == chunk_id
    assert retrieved.chunk_text == "Test content"


@pytest.mark.asyncio
async def test_list_by_file(adb: AsyncSession):
    """Test listar chunks por archivo."""
    file_id = await _create_valid_file_id(adb)
    
    chunks = [
        ChunkMetadata(
            file_id=file_id,
            chunk_index=i,
            chunk_text=f"Chunk {i}",
            token_count=10,
        )
        for i in range(5)
    ]
    
    await chunk_metadata_repository.insert_chunks(adb, chunks)
    
    result = await chunk_metadata_repository.list_by_file(adb, file_id)
    
    assert len(result) == 5
    # Verificar orden por chunk_index
    for i, chunk in enumerate(result):
        assert chunk.chunk_index == i


@pytest.mark.asyncio
async def test_count_by_file(adb: AsyncSession):
    """Test contar chunks por archivo."""
    file_id = await _create_valid_file_id(adb)
    
    chunks = [
        ChunkMetadata(
            file_id=file_id,
            chunk_index=i,
            chunk_text=f"Chunk {i}",
            token_count=10,
        )
        for i in range(7)
    ]
    
    await chunk_metadata_repository.insert_chunks(adb, chunks)
    
    count = await chunk_metadata_repository.count_by_file(adb, file_id)
    
    assert count == 7


@pytest.mark.asyncio
async def test_get_by_file_and_index(adb: AsyncSession):
    """Test obtener chunk específico por archivo e índice."""
    file_id = await _create_valid_file_id(adb)
    
    chunks = [
        ChunkMetadata(
            file_id=file_id,
            chunk_index=i,
            chunk_text=f"Chunk {i}",
            token_count=10,
        )
        for i in range(3)
    ]
    
    await chunk_metadata_repository.insert_chunks(adb, chunks)
    
    chunk = await chunk_metadata_repository.get_by_file_and_index(
        adb,
        file_id,
        chunk_index=1,
    )
    
    assert chunk is not None
    assert chunk.chunk_index == 1
    assert chunk.chunk_text == "Chunk 1"


@pytest.mark.asyncio
async def test_insert_chunks_persists_to_db_with_roundtrip(adb: AsyncSession):
    """Test insertar chunks y verificar persistencia real con commit y nuevo query."""
    file_id = await _create_valid_file_id(adb)
    
    chunks = [
        ChunkMetadata(
            file_id=file_id,
            chunk_index=i,
            chunk_text=f"Persistent chunk {i}",
            token_count=15,
        )
        for i in range(3)
    ]
    
    # Insertar chunks (la sesión de prueba maneja la transacción externamente)
    created = await chunk_metadata_repository.insert_chunks(adb, chunks)
    
    assert len(created) == 3
    
    # Verificar persistencia con nuevo list_by_file (roundtrip lógico dentro de la misma sesión)
    retrieved = await chunk_metadata_repository.list_by_file(adb, file_id)

    assert len(retrieved) == 3
    for i, chunk in enumerate(retrieved):
        assert chunk.chunk_index == i
        assert chunk.chunk_text == f"Persistent chunk {i}"
        assert chunk.token_count == 15
        assert chunk.chunk_id is not None
