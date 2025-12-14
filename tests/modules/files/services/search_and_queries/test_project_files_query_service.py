
# tests/modules/files/services/search_and_queries/test_project_files_query_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio ProjectFilesQueryService del módulo Files.

Objetivo del servicio (contrato esperado, laxo cuando no esté implementado todo):
- Listar **todos** los archivos de un proyecto (input + product) como una “unión”
  con un shape homogéneo (al menos: id, project_id, category, file_name, storage_path,
  size_bytes, created_at).
- Filtros:
  - category (input | product)
  - search (coincidencia por file_name o storage_path, case-insensitive)
  - include_archived (True/False), por defecto False
- Ordenamiento con campos whitelisted (p.ej. created_at, size_bytes, file_name).
- Paginación (limit/offset).
- Manejo de proyecto inexistente (retorna lista vacía).

Estos tests asumen que el servicio consulta una vista unificada (o equivalente en SQLAlchemy)
pero no dependen de su implementación interna exacta.
"""

import pytest
from datetime import datetime, timedelta

from app.modules.files.enums import FileCategory
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.services.project_files_query import ProjectFilesQueryService


def _mk_input(db, **over):
    from uuid import uuid4
    from app.modules.files.enums import FileType, StorageBackend, InputProcessingStatus
    
    # Generar path único basado en el file_name
    file_name = over.get("input_file_display_name", "input.txt")
    unique_path = over.get("input_file_storage_path") or f"users/uA/projects/{uuid4()}/input/{file_name}"
    
    base = dict(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=uuid4(),
        input_file_display_name=file_name,
        input_file_original_name=file_name,
        input_file_type=FileType.pdf,
        input_file_mime_type="application/pdf",
        input_file_storage_path=unique_path,
        input_file_category=FileCategory.input,
        input_file_size_bytes=100,
        input_file_storage_backend=StorageBackend.supabase,
        input_file_status=InputProcessingStatus.pending,
        input_file_is_active=True,
        input_file_is_archived=False,
        input_file_uploaded_at=datetime.utcnow() - timedelta(days=3),
    )
    base.update(over)
    obj = InputFile(**base)
    db.add(obj)
    return obj


def _mk_product(db, **over):
    from uuid import uuid4
    from app.modules.files.enums import ProductFileType, ProductVersion, StorageBackend
    
    # Generar path único basado en el file_name
    file_name = over.get("product_file_original_name", "product.pdf")
    unique_path = over.get("product_file_storage_path") or f"users/uA/projects/{uuid4()}/output/{file_name}"
    
    base = dict(
        product_file_id=uuid4(),
        project_id=uuid4(),
        product_file_generated_by=uuid4(),
        product_file_original_name=file_name,
        product_file_type=ProductFileType.document,
        product_file_mime_type="application/pdf",
        product_file_storage_path=unique_path,
        product_file_size_bytes=900,
        product_file_storage_backend=StorageBackend.supabase,
        product_file_version=ProductVersion.v1,
        product_file_is_active=True,
        product_file_is_archived=False,
        product_file_generated_at=datetime.utcnow() - timedelta(days=1),
    )
    base.update(over)
    obj = ProductFile(**base)
    db.add(obj)
    return obj


@pytest.fixture
async def seed_union(db_session, sample_project):
    """
    Siembra datos mixtos para el proyecto sample_project.
    """
    from uuid import uuid4
    # Proyecto principal (sample_project) - asegurar paths únicos
    _mk_input(
        db_session, 
        project_id=sample_project.project_id, 
        input_file_uploaded_by=uuid4(), 
        input_file_display_name="notes.txt", 
        input_file_storage_path=f"users/{uuid4()}/projects/{sample_project.project_id}/input/notes.txt",
        input_file_size_bytes=200, 
        input_file_uploaded_at=datetime.utcnow() - timedelta(days=5)
    )
    _mk_input(
        db_session, 
        project_id=sample_project.project_id, 
        input_file_uploaded_by=uuid4(), 
        input_file_display_name="data.csv", 
        input_file_storage_path=f"users/{uuid4()}/projects/{sample_project.project_id}/input/data.csv",
        input_file_size_bytes=1200, 
        input_file_uploaded_at=datetime.utcnow() - timedelta(days=4)
    )
    _mk_input(
        db_session, 
        project_id=sample_project.project_id, 
        input_file_uploaded_by=uuid4(), 
        input_file_display_name="draft.md", 
        input_file_storage_path=f"users/{uuid4()}/projects/{sample_project.project_id}/input/draft.md",
        input_file_size_bytes=400, 
        input_file_is_archived=True, 
        input_file_uploaded_at=datetime.utcnow() - timedelta(days=2)
    )
    _mk_product(
        db_session, 
        project_id=sample_project.project_id, 
        product_file_generated_by=uuid4(), 
        product_file_original_name="report.pdf", 
        product_file_storage_path=f"users/{uuid4()}/projects/{sample_project.project_id}/output/report.pdf",
        product_file_size_bytes=5000, 
        product_file_generated_at=datetime.utcnow() - timedelta(days=1)
    )
    _mk_product(
        db_session, 
        project_id=sample_project.project_id, 
        product_file_generated_by=uuid4(), 
        product_file_original_name="chart.png", 
        product_file_storage_path=f"users/{uuid4()}/projects/{sample_project.project_id}/output/chart.png",
        product_file_size_bytes=2500, 
        product_file_generated_at=datetime.utcnow() - timedelta(days=2)
    )
    
    await db_session.commit()
    return None


@pytest.mark.asyncio
async def test_list_project_files_returns_input_and_product(db_session, seed_union, sample_project):
    """
    Debe devolver resultados de ambas categorías para el proyecto sample_project.
    """
    svc = ProjectFilesQueryService(db=db_session)
    rows = await svc.list_project_files(project_id=sample_project.project_id)
    cats = {r.get("category") for r in rows}
    assert FileCategory.input in cats
    assert FileCategory.product_files in cats
    # No debe traer de otros proyectos
    assert all(r.get("project_id") == sample_project.project_id for r in rows)


@pytest.mark.asyncio
async def test_filter_by_category_input_only(db_session, seed_union, sample_project):
    """
    Debe filtrar por categoría input.
    """
    svc = ProjectFilesQueryService(db=db_session)
    rows = await svc.list_project_files(project_id=sample_project.project_id, category=FileCategory.input)
    assert len(rows) >= 2
    assert all(r.get("category") == FileCategory.input for r in rows)


@pytest.mark.asyncio
async def test_filter_by_category_product_only(db_session, seed_union, sample_project):
    """
    Debe filtrar por categoría product.
    """
    svc = ProjectFilesQueryService(db=db_session)
    rows = await svc.list_project_files(project_id=sample_project.project_id, category=FileCategory.product_files)
    assert len(rows) >= 1
    assert all(r.get("category") == FileCategory.product_files for r in rows)


@pytest.mark.asyncio
async def test_search_matches_filename_or_path_case_insensitive(db_session, seed_union, sample_project):
    """
    Debe permitir búsqueda por nombre o ruta (case-insensitive).
    """
    svc = ProjectFilesQueryService(db=db_session)
    # Busca 'data' debe captar data.csv
    rows = await svc.list_project_files(project_id=sample_project.project_id, search="DaTa")
    names = {r.get("file_name", "").lower() for r in rows}
    assert "data.csv" in names or any("data" in (r.get("storage_path", "").lower()) for r in rows)


@pytest.mark.asyncio
async def test_excludes_archived_by_default_but_can_include(db_session, seed_union, sample_project):
    """
    Por defecto excluye archivados; con include_archived=True los incluye.
    """
    svc = ProjectFilesQueryService(db=db_session)
    base = await svc.list_project_files(project_id=sample_project.project_id)
    names = {r.get("file_name") for r in base}
    assert "draft.md" not in names, "Archivado debe quedar fuera por defecto"

    with_arch = await svc.list_project_files(project_id=sample_project.project_id, include_archived=True)
    names_arch = {r.get("file_name") for r in with_arch}
    assert "draft.md" in names_arch, "Con include_archived=True debe incluirlo"


@pytest.mark.asyncio
async def test_sorting_by_whitelisted_fields(db_session, seed_union, sample_project):
    """
    Debe permitir ordenamiento por 'created_at' y 'size_bytes'.
    """
    svc = ProjectFilesQueryService(db=db_session)

    by_date = await svc.list_project_files(project_id=sample_project.project_id, order_by="created_at", descending=True)
    dates = [r.get("created_at") for r in by_date]
    assert dates == sorted(dates, reverse=True)

    by_size = await svc.list_project_files(project_id=sample_project.project_id, order_by="size_bytes", descending=False)
    sizes = [r.get("size_bytes", 0) for r in by_size]
    assert sizes == sorted(sizes)


@pytest.mark.asyncio
async def test_sorting_by_forbidden_field_raises(db_session, seed_union, sample_project):
    """
    Campos de ordenamiento no permitidos deben causar ValueError.
    """
    svc = ProjectFilesQueryService(db=db_session)
    with pytest.raises(ValueError):
        await svc.list_project_files(project_id=sample_project.project_id, order_by="drop_database_now")


@pytest.mark.asyncio
async def test_pagination_limit_offset_is_consistent(db_session, seed_union, sample_project):
    """
    Debe respetar limit y offset. Las páginas no deben solaparse si hay suficientes filas.
    """
    svc = ProjectFilesQueryService(db=db_session)

    p1 = await svc.list_project_files(project_id=sample_project.project_id, limit=2, offset=0, order_by="created_at", descending=False)
    p2 = await svc.list_project_files(project_id=sample_project.project_id, limit=2, offset=2, order_by="created_at", descending=False)

    ids1 = {r.get("id") for r in p1}
    ids2 = {r.get("id") for r in p2}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_nonexistent_project_returns_empty_list(db_session, seed_union):
    """
    Si el proyecto no existe (o no tiene archivos), debe devolver lista vacía.
    """
    from uuid import uuid4
    svc = ProjectFilesQueryService(db=db_session)
    rows = await svc.list_project_files(project_id=uuid4())
    assert rows == []


# Fin del archivo tests/modules/files/services/search_and_queries/test_project_files_query_service.py