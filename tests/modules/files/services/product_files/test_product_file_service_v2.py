# -*- coding: utf-8 -*-
"""
Tests para el servicio de product files v2.

Cubre:
- create_or_update_product_file (upsert por project + path)
- register_product_file_metadata
- get_product_file
- list_active_product_files
- archive_product_file
"""

import pytest
from uuid import uuid4

from app.modules.files.enums import ProductFileType
from app.modules.files.services.product_files.service import (
    create_or_update_product_file,
    register_product_file_metadata,
    get_product_file,
    list_active_product_files,
    archive_product_file,
)
from app.modules.files.schemas.product_file_schemas import ProductFileCreate


@pytest.mark.asyncio
async def test_create_or_update_product_file(db_session):
    """Debe crear ProductFile y FilesBase, o actualizar si ya existe."""
    project_id = uuid4()
    
    data = ProductFileCreate(
        project_id=project_id,
        product_file_name="output.pdf",
        product_file_display_name="output.pdf",
        product_file_mime_type="application/pdf",
        product_file_size_bytes=2048,
        product_file_type=ProductFileType.report,
        product_file_storage_path="/products/output.pdf",
    )
    
    product_file, files_base = await create_or_update_product_file(
        session=db_session,
        data=data,
        file_type=ProductFileType.report,
        mime_type="application/pdf",
        file_size_bytes=2048,
    )
    
    assert product_file is not None
    assert product_file.project_id == project_id
    assert product_file.file_id is not None
    assert product_file.product_file_type == ProductFileType.report
    
    assert files_base is not None
    assert files_base.project_id == project_id
    assert files_base.product_file_id == product_file.product_file_id
    
    # Upsert: mismo project_id + path debería actualizar
    product_file2, files_base2 = await create_or_update_product_file(
        session=db_session,
        data=data,
        file_type=ProductFileType.report,
        mime_type="application/pdf",
        file_size_bytes=3000,  # tamaño diferente
    )
    
    assert product_file2.product_file_id == product_file.product_file_id
    assert product_file2.product_file_size_bytes == 3000


@pytest.mark.asyncio
async def test_register_product_file_metadata(db_session):
    """Debe registrar metadatos para un ProductFile."""
    project_id = uuid4()
    
    data = ProductFileCreate(
        project_id=project_id,
        product_file_name="report.pdf",
        product_file_display_name="report.pdf",
        product_file_mime_type="application/pdf",
        product_file_size_bytes=1024,
        product_file_type=ProductFileType.report,
        product_file_storage_path="/products/report.pdf",
    )
    
    product_file, _ = await create_or_update_product_file(
        session=db_session,
        data=data,
        file_type=ProductFileType.report,
        mime_type="application/pdf",
        file_size_bytes=1024,
    )
    
    await db_session.commit()
    
    metadata = await register_product_file_metadata(
        session=db_session,
        product_file_id=product_file.product_file_id,
        metadata_kwargs={
            "page_count": 10,
            "word_count": 500,
        },
    )
    
    assert metadata is not None
    assert metadata.product_file_id == product_file.product_file_id
    assert metadata.page_count == 10


@pytest.mark.asyncio
async def test_get_product_file(db_session):
    """Debe obtener ProductFile por ID o None."""
    project_id = uuid4()
    
    data = ProductFileCreate(
        project_id=project_id,
        product_file_name="chart.png",
        product_file_display_name="chart.png",
        product_file_mime_type="image/png",
        product_file_size_bytes=512,
        product_file_type=ProductFileType.chart,
        product_file_storage_path="/products/chart.png",
    )
    
    product_file, _ = await create_or_update_product_file(
        session=db_session,
        data=data,
        file_type=ProductFileType.chart,
        mime_type="image/png",
        file_size_bytes=512,
    )
    
    await db_session.commit()
    
    found = await get_product_file(db_session, product_file.product_file_id)
    assert found is not None
    assert found.product_file_id == product_file.product_file_id
    
    not_found = await get_product_file(db_session, uuid4())
    assert not_found is None


@pytest.mark.asyncio
async def test_list_active_product_files(db_session):
    """Debe listar archivos producto activos de un proyecto."""
    project_id = uuid4()
    
    # Crear 2 archivos activos
    for i in range(2):
        data = ProductFileCreate(
            project_id=project_id,
            product_file_name=f"output{i}.pdf",
            product_file_display_name=f"output{i}.pdf",
            product_file_mime_type="application/pdf",
            product_file_size_bytes=1000,
            product_file_type=ProductFileType.report,
            product_file_storage_path=f"/products/output{i}.pdf",
        )
        await create_or_update_product_file(
            session=db_session,
            data=data,
            file_type=ProductFileType.report,
            mime_type="application/pdf",
            file_size_bytes=1000,
        )
    
    await db_session.commit()
    
    files = await list_active_product_files(db_session, project_id)
    assert len(files) == 2


@pytest.mark.asyncio
async def test_archive_product_file(db_session):
    """Debe archivar ProductFile (desactivar)."""
    project_id = uuid4()
    
    data = ProductFileCreate(
        project_id=project_id,
        product_file_name="old_report.pdf",
        product_file_display_name="old_report.pdf",
        product_file_mime_type="application/pdf",
        product_file_size_bytes=1024,
        product_file_type=ProductFileType.report,
        product_file_storage_path="/products/old_report.pdf",
    )
    
    product_file, _ = await create_or_update_product_file(
        session=db_session,
        data=data,
        file_type=ProductFileType.report,
        mime_type="application/pdf",
        file_size_bytes=1024,
    )
    
    await db_session.commit()
    
    archived = await archive_product_file(db_session, product_file.product_file_id)
    await db_session.commit()
    
    assert archived is not None
    assert archived.product_file_is_archived is True
    assert archived.product_file_is_active is False


# Fin del archivo
