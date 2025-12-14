# -*- coding: utf-8 -*-
"""
Tests para las fachadas funcionales de product files v2.

Cubre:
- create_product_file
- get_product_file_details
- list_project_product_files
- get_product_file_download_url
- archive_product_file
"""

import pytest
from uuid import uuid4

from app.modules.files.facades.product_files import (
    create_product_file,
    get_product_file_details,
    list_project_product_files,
    get_product_file_download_url,
    archive_product_file,
)
from app.modules.files.schemas import ProductFileResponse
from app.modules.files.enums import ProductFileType, StorageBackend, ProductVersion


@pytest.mark.asyncio
async def test_create_product_file(db_session, mock_storage):
    """Debe crear un archivo producto."""
    project_id = uuid4()
    generated_by = uuid4()
    file_bytes = b"pdf content"
    storage_key = f"{project_id}/product/output.pdf"
    
    result = await create_product_file(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        project_id=project_id,
        generated_by=generated_by,
        file_bytes=file_bytes,
        storage_key=storage_key,
        original_name="output.pdf",
        mime_type="application/pdf",
        file_type=ProductFileType.report,
        storage_backend=StorageBackend.supabase,
    )
    
    assert isinstance(result, ProductFileResponse)
    assert result.product_file_id is not None
    assert result.original_name == "output.pdf"


@pytest.mark.asyncio
async def test_get_product_file_details(db_session, mock_storage):
    """Debe obtener detalles de un archivo producto."""
    project_id = uuid4()
    generated_by = uuid4()
    file_bytes = b"content"
    storage_key = f"{project_id}/product/report.pdf"
    
    created = await create_product_file(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        project_id=project_id,
        generated_by=generated_by,
        file_bytes=file_bytes,
        storage_key=storage_key,
        original_name="report.pdf",
        mime_type="application/pdf",
        file_type=ProductFileType.report,
        storage_backend=StorageBackend.supabase,
    )
    
    await db_session.commit()
    
    details = await get_product_file_details(
        db=db_session,
        product_file_id=created.product_file_id,
    )
    
    assert isinstance(details, ProductFileResponse)
    assert details.product_file_id == created.product_file_id


@pytest.mark.asyncio
async def test_list_project_product_files(db_session, mock_storage):
    """Debe listar archivos producto de un proyecto."""
    project_id = uuid4()
    generated_by = uuid4()
    
    # Crear 2 archivos
    for i in range(2):
        storage_key = f"{project_id}/product/output{i}.pdf"
        file_bytes = b"content"
        
        await create_product_file(
            db=db_session,
            storage_client=mock_storage,
            bucket_name="users-files",
            project_id=project_id,
            generated_by=generated_by,
            file_bytes=file_bytes,
            storage_key=storage_key,
            original_name=f"output{i}.pdf",
            mime_type="application/pdf",
            file_type=ProductFileType.report,
            storage_backend=StorageBackend.supabase,
        )
    
    await db_session.commit()
    
    files = await list_project_product_files(db=db_session, project_id=project_id)
    assert len(files) >= 2
    assert all(isinstance(f, ProductFileResponse) for f in files)


@pytest.mark.asyncio
async def test_get_product_file_download_url(db_session, mock_storage):
    """Debe generar URL de descarga para un archivo producto."""
    project_id = uuid4()
    generated_by = uuid4()
    file_bytes = b"content"
    storage_key = f"{project_id}/product/download.pdf"
    
    created = await create_product_file(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        project_id=project_id,
        generated_by=generated_by,
        file_bytes=file_bytes,
        storage_key=storage_key,
        original_name="download.pdf",
        mime_type="application/pdf",
        file_type=ProductFileType.report,
        storage_backend=StorageBackend.supabase,
    )
    
    await db_session.commit()
    
    url = await get_product_file_download_url(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        product_file_id=created.product_file_id,
    )
    
    assert url is not None
    assert isinstance(url, str)
    assert "mockstorage" in url


@pytest.mark.asyncio
async def test_archive_product_file(db_session, mock_storage):
    """Debe archivar un archivo producto."""
    project_id = uuid4()
    generated_by = uuid4()
    file_bytes = b"content"
    storage_key = f"{project_id}/product/old.pdf"
    
    created = await create_product_file(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        project_id=project_id,
        generated_by=generated_by,
        file_bytes=file_bytes,
        storage_key=storage_key,
        original_name="old.pdf",
        mime_type="application/pdf",
        file_type=ProductFileType.report,
        storage_backend=StorageBackend.supabase,
    )
    
    await db_session.commit()
    
    # archive_product_file no devuelve nada útil
    await archive_product_file(
        db=db_session,
        storage_client=mock_storage,
        bucket_name="users-files",
        product_file_id=created.product_file_id,
    )
    
    # Verificar que el archivo está archivado
    details = await get_product_file_details(
        db=db_session,
        product_file_id=created.product_file_id,
    )
    assert details.is_archived is True


# Fin del archivo
