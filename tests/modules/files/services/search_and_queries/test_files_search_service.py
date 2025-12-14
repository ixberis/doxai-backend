
# tests/modules/files/services/search_and_queries/test_files_search_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio FilesSearchService del módulo Files.

Cubre:
- Búsqueda combinada de InputFile y ProductFile (unión o filtro por categoría).
- Filtros por categoría, tipo, idioma, versión, fechas.
- Ordenamiento por columnas permitidas.
- Rechazo de sort por columnas no permitidas.
- Retorno de resultados vacíos (lista vacía).
- Paginación (limit/offset) y consistencia.
"""

import pytest
from datetime import datetime, timedelta
from random import randint

from app.modules.files.enums import FileCategory, FileLanguage, ProductVersion, FileType, ProductFileType, StorageBackend
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.services.files_search_service import FilesSearchService


@pytest.fixture
async def seed_files(db_session, sample_project, sample_user):
    """Crea datos mixtos de input y product files."""
    from uuid import uuid4, UUID
    now = datetime.utcnow()

    # Usamos directamente el project_id del fixture (ya es UUID)
    project_uuid: UUID = sample_project.project_id
    # Para simplificar y evitar problemas de conversión, generamos un UUID sintético
    # para el campo input_file_uploaded_by / product_file_generated_by
    user_uuid: UUID = uuid4()

    inputs = [
        InputFile(
            input_file_id=uuid4(),
            project_id=project_uuid,
            input_file_uploaded_by=user_uuid,
            input_file_display_name=f"input_{i}.txt",
            input_file_original_name=f"input_{i}.txt",
            input_file_mime_type="application/pdf",
            input_file_category=FileCategory.input,
            input_file_language=FileLanguage.en if i % 2 == 0 else FileLanguage.es,
            input_file_uploaded_at=now - timedelta(days=i),
            input_file_size_bytes=randint(100, 5000),
            input_file_storage_path=f"input_{i}.txt",
            input_file_type=FileType.pdf,
            input_file_storage_backend=StorageBackend.supabase,
        )
        for i in range(5)
    ]
    products = [
        ProductFile(
            product_file_id=uuid4(),
            project_id=project_uuid,
            product_file_generated_by=user_uuid,
            product_file_original_name=f"product_{i}.pdf",
            product_file_mime_type="application/pdf",
            product_file_version=ProductVersion.v1,
            product_file_generated_at=now - timedelta(days=i),
            product_file_size_bytes=randint(5000, 10000),
            product_file_storage_path=f"product_{i}.pdf",
            product_file_type=ProductFileType.document,
            product_file_storage_backend=StorageBackend.supabase,
        )
        for i in range(5)
    ]
    for f in inputs + products:
        db_session.add(f)
    await db_session.commit()
    return inputs, products


@pytest.mark.asyncio
async def test_search_all_returns_mixed_categories(db_session, seed_files, sample_project):
    """
    Debe devolver registros de ambas categorías (input y product).
    """
    svc = FilesSearchService(db=db_session)
    results = await svc.search(project_id=sample_project.project_id)
    # Verificar que hay InputFiles y ProductFiles
    has_input = any(isinstance(r, InputFile) for r in results)
    has_product = any(isinstance(r, ProductFile) for r in results)
    assert has_input
    assert has_product


@pytest.mark.asyncio
async def test_search_filter_by_category(db_session, seed_files, sample_project):
    """
    Debe permitir filtrar sólo por categoría específica.
    """
    svc = FilesSearchService(db=db_session)
    results = await svc.search(project_id=sample_project.project_id, category=FileCategory.product_files)
    # Para product_files, verificar que todos son ProductFile
    assert all(isinstance(r, ProductFile) for r in results)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_search_filter_by_language(db_session, seed_files, sample_project):
    """
    Debe filtrar por idioma si se proporciona (sólo para InputFiles).
    """
    svc = FilesSearchService(db=db_session)
    results = await svc.search(project_id=sample_project.project_id, language=FileLanguage.es)
    assert all(
        getattr(r, "input_file_language", None) in (FileLanguage.es, None) for r in results
    )


@pytest.mark.asyncio
async def test_search_filter_by_version(db_session, seed_files, sample_project):
    """
    Debe permitir filtrar por versión (para ProductFiles).
    """
    svc = FilesSearchService(db=db_session)
    results = await svc.search(project_id=sample_project.project_id, version=ProductVersion.v1)
    assert all(
        getattr(r, "product_file_version", ProductVersion.v1) == ProductVersion.v1
        for r in results
    )


@pytest.mark.asyncio
async def test_search_order_by_allowed_field(db_session, seed_files):
    """
    Debe permitir ordenamiento por campos whitelisted (created_at, size_bytes).
    """
    svc = FilesSearchService(db=db_session)
    results = await svc.search(project_id=1, order_by="created_at", descending=True)
    dates = [getattr(r, "input_file_uploaded_at", None) or getattr(r, "product_file_generated_at", None) for r in results]
    dates = [d for d in dates if d is not None]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.asyncio
async def test_search_order_by_forbidden_field_raises_valueerror(db_session):
    """
    Debe rechazar ordenamiento por campos no permitidos.
    """
    svc = FilesSearchService(db=db_session)
    with pytest.raises(ValueError):
        await svc.search(project_id=1, order_by="drop_table_users")


@pytest.mark.asyncio
async def test_search_returns_empty_list_when_no_matches(db_session):
    """
    Si no hay coincidencias con los filtros, debe retornar lista vacía.
    """
    svc = FilesSearchService(db=db_session)
    results = await svc.search(project_id=1, category=FileCategory.product_files, language=FileLanguage.fr)
    assert results == []


@pytest.mark.asyncio
async def test_search_pagination_limit_offset(db_session, seed_files):
    """
    Debe soportar limit y offset coherentes.
    """
    svc = FilesSearchService(db=db_session)
    page1 = await svc.search(project_id=1, limit=3, offset=0)
    page2 = await svc.search(project_id=1, limit=3, offset=3)
    assert all(getattr(x, 'input_file_id', None) or getattr(x, 'product_file_id', None) for x in page1)
    assert all(getattr(x, 'input_file_id', None) or getattr(x, 'product_file_id', None) for x in page2)
    # No deben solaparse los IDs si hay suficientes registros
    ids1 = {getattr(x, 'input_file_id', None) or getattr(x, 'product_file_id', None) for x in page1}
    ids2 = {getattr(x, 'input_file_id', None) or getattr(x, 'product_file_id', None) for x in page2}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_search_filter_by_date_range(db_session, seed_files):
    """
    Debe permitir filtro por rango de fechas (desde - hasta).
    """
    svc = FilesSearchService(db=db_session)
    now = datetime.utcnow()
    start = now - timedelta(days=2)
    end = now + timedelta(days=1)
    results = await svc.search(project_id=1, date_from=start, date_to=end)
    for r in results:
        created = getattr(r, 'input_file_uploaded_at', None) or getattr(r, 'product_file_generated_at', None)
        if created:
            assert start <= created <= end


# Fin del archivo tests/modules/files/services/search_and_queries/test_files_search_service.py
