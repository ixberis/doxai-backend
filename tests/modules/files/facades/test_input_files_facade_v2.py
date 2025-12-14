# -*- coding: utf-8 -*-
"""
Tests para la fachada de input files v2 (InputFilesFacade).

Cubre:
- upload_input_file (con validaciones)
- list_project_input_files (por proyecto)
- get_input_file_by_file_id (por file_id)
- get_download_url_for_file
- delete_input_file (soft y hard)
"""

import pytest
from uuid import uuid4

from app.modules.files.facades.input_files import InputFilesFacade
from app.modules.files.schemas import InputFileUpload, InputFileResponse
from app.modules.files.enums import (
    StorageBackend,
    FileType,
    FileCategory,
    IngestSource,
    InputFileClass,
    Language,
)


@pytest.mark.asyncio
async def test_upload_input_file(db_session, mock_storage):
    """Debe subir un archivo insumo y registrarlo."""
    facade = InputFilesFacade(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        storage_backend=StorageBackend.supabase,
    )
    
    project_id = uuid4()
    uploaded_by = uuid4()
    file_bytes = b"test content"
    storage_key = f"{project_id}/input/test.pdf"
    
    upload_dto = InputFileUpload(
        project_id=project_id,
        original_name="test.pdf",
        display_name="Test PDF",
        mime_type="application/pdf",
        size_bytes=len(file_bytes),
        file_type=FileType.document,
        file_category=FileCategory.input,
        ingest_source=IngestSource.upload,
        language=Language.es,
        input_file_class=InputFileClass.source,
    )
    
    result = await facade.upload_input_file(
        upload=upload_dto,
        uploaded_by=uploaded_by,
        file_bytes=file_bytes,
        storage_key=storage_key,
    )
    
    assert isinstance(result, InputFileResponse)
    assert result.input_file_id is not None
    assert result.original_name == "test.pdf"


@pytest.mark.asyncio
async def test_list_input_files_by_project(db_session, mock_storage):
    """Debe listar archivos insumo de un proyecto."""
    facade = InputFilesFacade(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        storage_backend=StorageBackend.supabase,
    )
    
    project_id = uuid4()
    uploaded_by = uuid4()
    
    # Subir algunos archivos
    for i in range(2):
        storage_key = f"{project_id}/input/file{i}.txt"
        file_bytes = b"content"
        
        upload_dto = InputFileUpload(
            project_id=project_id,
            original_name=f"file{i}.txt",
            display_name=f"File {i}",
            mime_type="text/plain",
            size_bytes=len(file_bytes),
            file_type=FileType.document,
            file_category=FileCategory.input,
            ingest_source=IngestSource.upload,
            input_file_class=InputFileClass.source,
        )
        
        await facade.upload_input_file(
            upload=upload_dto,
            uploaded_by=uploaded_by,
            file_bytes=file_bytes,
            storage_key=storage_key,
        )
    
    await db_session.commit()
    
    files = await facade.list_project_input_files(project_id=project_id)
    assert len(files) >= 2
    assert all(isinstance(f, InputFileResponse) for f in files)


@pytest.mark.asyncio
async def test_get_input_file_by_id(db_session, mock_storage):
    """Debe obtener un archivo insumo por su ID."""
    facade = InputFilesFacade(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        storage_backend=StorageBackend.supabase,
    )
    
    project_id = uuid4()
    uploaded_by = uuid4()
    file_bytes = b"pdf content"
    storage_key = f"{project_id}/input/doc.pdf"
    
    upload_dto = InputFileUpload(
        project_id=project_id,
        original_name="doc.pdf",
        display_name="Document PDF",
        mime_type="application/pdf",
        size_bytes=len(file_bytes),
        file_type=FileType.document,
        file_category=FileCategory.input,
        ingest_source=IngestSource.upload,
        input_file_class=InputFileClass.source,
    )
    
    result = await facade.upload_input_file(
        upload=upload_dto,
        uploaded_by=uploaded_by,
        file_bytes=file_bytes,
        storage_key=storage_key,
    )
    
    await db_session.commit()
    
    file_id = result.file_id or result.input_file_id
    
    found = await facade.get_input_file_by_file_id(file_id=file_id)
    assert isinstance(found, InputFileResponse)
    assert found.input_file_id == result.input_file_id


@pytest.mark.asyncio
async def test_get_download_url(db_session, mock_storage):
    """Debe generar URL de descarga para un archivo insumo."""
    facade = InputFilesFacade(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        storage_backend=StorageBackend.supabase,
    )
    
    project_id = uuid4()
    uploaded_by = uuid4()
    file_bytes = b"content"
    storage_key = f"{project_id}/input/download_me.pdf"
    
    upload_dto = InputFileUpload(
        project_id=project_id,
        original_name="download_me.pdf",
        mime_type="application/pdf",
        size_bytes=len(file_bytes),
        file_type=FileType.document,
        file_category=FileCategory.input,
        ingest_source=IngestSource.upload,
        input_file_class=InputFileClass.source,
    )
    
    result = await facade.upload_input_file(
        upload=upload_dto,
        uploaded_by=uploaded_by,
        file_bytes=file_bytes,
        storage_key=storage_key,
    )
    
    await db_session.commit()
    
    file_id = result.file_id or result.input_file_id
    
    url = await facade.get_download_url_for_file(file_id=file_id)
    assert url is not None
    assert isinstance(url, str)
    assert "mockstorage" in url


@pytest.mark.asyncio
async def test_delete_input_file_soft(db_session, mock_storage):
    """Debe archivar (soft delete) un archivo insumo."""
    facade = InputFilesFacade(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        storage_backend=StorageBackend.supabase,
    )
    
    project_id = uuid4()
    uploaded_by = uuid4()
    file_bytes = b"content"
    storage_key = f"{project_id}/input/delete_me.txt"
    
    upload_dto = InputFileUpload(
        project_id=project_id,
        original_name="delete_me.txt",
        mime_type="text/plain",
        size_bytes=len(file_bytes),
        file_type=FileType.document,
        file_category=FileCategory.input,
        ingest_source=IngestSource.upload,
        input_file_class=InputFileClass.source,
    )
    
    result = await facade.upload_input_file(
        upload=upload_dto,
        uploaded_by=uploaded_by,
        file_bytes=file_bytes,
        storage_key=storage_key,
    )
    
    await db_session.commit()
    
    file_id = result.file_id or result.input_file_id
    
    # delete_input_file no devuelve nada útil, solo verificamos que no levanta excepción
    await facade.delete_input_file(file_id=file_id, hard_delete=False)
    
    # Verificar que el archivo está archivado
    found = await facade.get_input_file_by_file_id(file_id=file_id)
    assert found.is_archived is True


# Fin del archivo
