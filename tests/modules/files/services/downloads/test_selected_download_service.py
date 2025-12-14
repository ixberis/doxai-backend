
# tests/modules/files/services/downloads/test_selected_download_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio SelectedDownloadService del módulo Files.

Cubre:
- Preparación de descarga de uno o varios archivos seleccionados.
- Validación de permisos de proyecto.
- Filtrado por categorías permitidas (input/product).
- Generación de manifiesto (lista de rutas y tamaños).
- Manejo de errores en archivos inexistentes.
- Descarga vacía si no se selecciona nada.
"""

import pytest
from random import randint

from app.modules.files.enums import FileCategory
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.services.selected_download_service import SelectedDownloadService


@pytest.fixture
async def seed_files(db_session, sample_project, sample_user):
    """Crea archivos mixtos (input y product) para pruebas de selección."""
    from uuid import uuid4, UUID
    
    # Convertir IDs a UUID si es necesario
    proj_id = sample_project.project_id if isinstance(sample_project.project_id, UUID) else UUID(str(sample_project.project_id))
    
    # Crear un UUID único para el usuario (ya que AppUser.user_id es int)
    user_uuid = uuid4()
    
    from app.modules.files.enums import FileType, ProductFileType, ProductVersion, StorageBackend
    
    inputs = [
        InputFile(
            input_file_id=uuid4(),
            project_id=proj_id,
            input_file_uploaded_by=user_uuid,
            input_file_original_name=f"in_{i}.txt",
            input_file_display_name=f"in_{i}.txt",
            input_file_mime_type="text/plain",
            input_file_type=FileType.txt,
            input_file_storage_path=f"users/u66/projects/{proj_id}/input/in_{i}.txt",
            input_file_size_bytes=randint(100, 1000),
            input_file_storage_backend=StorageBackend.supabase,
            input_file_is_active=True,
            input_file_is_archived=False,
        )
        for i in range(3)
    ]
    products = [
        ProductFile(
            product_file_id=uuid4(),
            project_id=proj_id,
            product_file_generated_by=user_uuid,
            product_file_original_name=f"out_{i}.pdf",
            product_file_display_name=f"out_{i}.pdf",
            product_file_mime_type="application/pdf",
            product_file_type=ProductFileType.document,
            product_file_version=ProductVersion.v1,
            product_file_storage_path=f"users/u66/projects/{proj_id}/output/out_{i}.pdf",
            product_file_size_bytes=randint(500, 2000),
            product_file_storage_backend=StorageBackend.supabase,
            product_file_is_active=True,
            product_file_is_archived=False,
        )
        for i in range(2)
    ]
    for f in inputs + products:
        db_session.add(f)
    await db_session.commit()
    return inputs, products


@pytest.fixture
def fake_project_service():
    """Simula un validador de acceso a proyectos."""
    class FakeProjectAccess:
        async def validate_user_access(self, project_id: int, user_id: str) -> bool:
            if project_id == 999:  # simula denegado
                raise PermissionError("Acceso denegado")
            return True

    return FakeProjectAccess()


@pytest.mark.asyncio
async def test_prepare_selected_download_happy_path(db_session, seed_files, fake_project_service, sample_project, sample_user):
    """
    Debe preparar correctamente el manifiesto de descarga con múltiples archivos.
    """
    inputs, products = seed_files
    svc = SelectedDownloadService(db=db_session, project_service=fake_project_service)
    user_id = sample_user.user_id
    project_id = sample_project.project_id
    selected_ids = [inputs[0].input_file_id, products[0].product_file_id]

    manifest = await svc.prepare_selected_download(project_id=project_id, user_id=user_id, file_ids=selected_ids)

    assert isinstance(manifest, dict)
    assert "project_id" in manifest
    assert manifest["project_id"] == project_id
    assert "files" in manifest
    files = manifest["files"]
    assert isinstance(files, list)
    assert len(files) == 2
    for f in files:
        assert "storage_path" in f
        assert "size_bytes" in f
        assert f["category"] in (FileCategory.input, FileCategory.product)


@pytest.mark.asyncio
async def test_prepare_selected_download_handles_missing_files(db_session, fake_project_service):
    """
    Si alguno de los archivos seleccionados no existe, debe excluirlo sin romper.
    """
    svc = SelectedDownloadService(db=db_session, project_service=fake_project_service)
    user_id = "user_2"
    project_id = 66
    manifest = await svc.prepare_selected_download(project_id=project_id, user_id=user_id, file_ids=[999999])
    assert isinstance(manifest, dict)
    assert manifest["files"] == []


@pytest.mark.asyncio
async def test_prepare_selected_download_permission_denied_raises(db_session, fake_project_service):
    """
    Si el usuario no tiene acceso al proyecto, debe lanzar PermissionError.
    """
    svc = SelectedDownloadService(db=db_session, project_service=fake_project_service)
    with pytest.raises(PermissionError):
        await svc.prepare_selected_download(project_id=999, user_id="x", file_ids=[1, 2])


@pytest.mark.asyncio
async def test_prepare_selected_download_empty_selection_returns_empty_manifest(db_session, fake_project_service):
    """
    Si la lista de archivos está vacía, debe devolver manifiesto vacío válido.
    """
    svc = SelectedDownloadService(db=db_session, project_service=fake_project_service)
    manifest = await svc.prepare_selected_download(project_id=66, user_id="user_3", file_ids=[])
    assert isinstance(manifest, dict)
    assert manifest["files"] == []


@pytest.mark.asyncio
async def test_prepare_selected_download_filters_invalid_categories(db_session, seed_files, fake_project_service, sample_project, sample_user):
    """
    Si existen archivos archivados o inactivos, el servicio debe ignorarlos sin fallar.
    """
    from uuid import uuid4, UUID
    
    # Convertir IDs
    proj_id = sample_project.project_id if isinstance(sample_project.project_id, UUID) else UUID(str(sample_project.project_id))
    user_uuid = uuid4()  # Crear UUID único para el usuario
    
    svc = SelectedDownloadService(db=db_session, project_service=fake_project_service)
    user_id = sample_user.user_id
    project_id = sample_project.project_id
    
    # Añadimos un registro archivado que debe ser filtrado
    from app.modules.files.models.input_file_models import InputFile
    from app.modules.files.enums import FileType, StorageBackend
    archived = InputFile(
        input_file_id=uuid4(),
        project_id=proj_id,
        input_file_uploaded_by=user_uuid,
        input_file_original_name="archived.tmp",
        input_file_display_name="archived.tmp",
        input_file_mime_type="text/plain",
        input_file_type=FileType.txt,
        input_file_storage_path="users/u66/projects/66/input/archived.tmp",
        input_file_size_bytes=10,
        input_file_storage_backend=StorageBackend.supabase,
        input_file_is_archived=True,  # Archivo archivado - debe ser filtrado
        input_file_is_active=False,   # Archivo inactivo
    )
    db_session.add(archived)
    await db_session.flush()

    # Intentar descargar el archivo archivado debe resultar en manifiesto vacío
    manifest = await svc.prepare_selected_download(project_id=project_id, user_id=user_id, file_ids=[archived.input_file_id])
    assert manifest["files"] == []


# Fin del archivo tests/modules/files/services/downloads/test_selected_download_service.py
