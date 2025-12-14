# -*- coding: utf-8 -*-
"""
Tests para el servicio de input files v2.

Cubre:
- register_uploaded_input_file (registro completo con files_base y metadata)
- get_input_file
- list_project_input_files (con/sin archivados)
- archive_input_file / unarchive_input_file
"""

import pytest
from uuid import uuid4

from app.modules.files.enums import StorageBackend, InputProcessingStatus
from app.modules.files.services.input_files.service import (
    register_uploaded_input_file,
    get_input_file,
    list_project_input_files,
    archive_input_file,
    unarchive_input_file,
)
from app.modules.files.schemas.input_file_schemas import InputFileUpload


@pytest.mark.asyncio
async def test_register_uploaded_input_file(db_session):
    """Debe crear InputFile, FilesBase y metadata opcional."""
    project_id = uuid4()
    uploaded_by = uuid4()
    
    upload = InputFileUpload(
        project_id=project_id,
        original_name="doc.pdf",
        display_name="doc.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        file_type="pdf",
    )
    
    input_file, files_base, metadata = await register_uploaded_input_file(
        session=db_session,
        upload=upload,
        uploaded_by=uploaded_by,
        storage_backend=StorageBackend.supabase,
        storage_path="/inputs/doc.pdf",
        file_extension=".pdf",
        checksum="abc123",
    )
    
    assert input_file is not None
    assert input_file.project_id == project_id
    assert input_file.input_file_uploaded_by == uploaded_by
    assert input_file.file_id is not None  # vinculado a files_base
    
    assert files_base is not None
    assert files_base.project_id == project_id
    assert files_base.input_file_id == input_file.input_file_id
    
    assert metadata is not None  # porque pasamos checksum
    assert metadata.input_file_id == input_file.input_file_id


@pytest.mark.asyncio
async def test_get_input_file(db_session):
    """Debe obtener InputFile por ID o None."""
    project_id = uuid4()
    uploaded_by = uuid4()
    
    upload = InputFileUpload(
        project_id=project_id,
        original_name="test.txt",
        display_name="test.txt",
        mime_type="text/plain",
        size_bytes=100,
        file_type="txt",
    )
    
    input_file, _, _ = await register_uploaded_input_file(
        session=db_session,
        upload=upload,
        uploaded_by=uploaded_by,
        storage_backend=StorageBackend.supabase,
        storage_path="/inputs/test.txt",
        file_extension=".txt",
    )
    
    await db_session.commit()
    
    # Obtener existente
    found = await get_input_file(db_session, input_file.input_file_id)
    assert found is not None
    assert found.input_file_id == input_file.input_file_id
    
    # Obtener inexistente
    not_found = await get_input_file(db_session, uuid4())
    assert not_found is None


@pytest.mark.asyncio
async def test_list_project_input_files(db_session):
    """Debe listar archivos de un proyecto (activos por defecto)."""
    project_id = uuid4()
    uploaded_by = uuid4()
    
    # Crear 2 archivos activos
    for i in range(2):
        upload = InputFileUpload(
            project_id=project_id,
            original_name=f"file{i}.txt",
            display_name=f"file{i}.txt",
            mime_type="text/plain",
            size_bytes=100,
            file_type="txt",
        )
        await register_uploaded_input_file(
            session=db_session,
            upload=upload,
            uploaded_by=uploaded_by,
            storage_backend=StorageBackend.supabase,
            storage_path=f"/inputs/file{i}.txt",
            file_extension=".txt",
        )
    
    await db_session.commit()
    
    files = await list_project_input_files(db_session, project_id)
    assert len(files) == 2


@pytest.mark.asyncio
async def test_archive_and_unarchive_input_file(db_session):
    """Debe archivar y desarchivar InputFile."""
    project_id = uuid4()
    uploaded_by = uuid4()
    
    upload = InputFileUpload(
        project_id=project_id,
        original_name="archive_me.pdf",
        display_name="archive_me.pdf",
        mime_type="application/pdf",
        size_bytes=500,
        file_type="pdf",
    )
    
    input_file, _, _ = await register_uploaded_input_file(
        session=db_session,
        upload=upload,
        uploaded_by=uploaded_by,
        storage_backend=StorageBackend.supabase,
        storage_path="/inputs/archive_me.pdf",
        file_extension=".pdf",
    )
    
    await db_session.commit()
    
    # Archivar
    archived = await archive_input_file(db_session, input_file.input_file_id)
    await db_session.commit()
    
    assert archived is not None
    assert archived.input_file_is_archived is True
    assert archived.input_file_is_active is False
    
    # Desarchivar
    unarchived = await unarchive_input_file(db_session, input_file.input_file_id)
    await db_session.commit()
    
    assert unarchived is not None
    assert unarchived.input_file_is_archived is False
    assert unarchived.input_file_is_active is True


# Fin del archivo
