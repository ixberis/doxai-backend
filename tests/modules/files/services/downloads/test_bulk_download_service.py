
# tests/modules/files/services/downloads/test_bulk_download_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio BulkDownloadService del módulo Files.

Cubre:
- Generación de un ZIP temporal con múltiples archivos (input + product).
- Validación de permisos de proyecto.
- Filtrado opcional por categoría (input, product).
- Excepciones cuando no hay archivos disponibles.
- Integración con el gateway de almacenamiento simulado.
- Registro del evento de descarga (si el servicio lo hace).
"""

import io
import zipfile
import pytest
from random import randint

from app.modules.files.enums import FileCategory
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.models.product_file_models import ProductFile
from app.modules.files.services.bulk_download_service import BulkDownloadService


@pytest.fixture
def fake_storage_gateway(tmp_path):
    """Simula un gateway que puede descargar archivos existentes."""
    class FakeStorageGateway:
        def __init__(self, root):
            self.root = root
            self.files = {}

        async def download(self, path: str) -> bytes:
            if path not in self.files:
                raise FileNotFoundError(path)
            return self.files[path]

        def preload(self, path: str, data: bytes):
            self.files[path] = data

    return FakeStorageGateway(tmp_path)


@pytest.fixture
async def seed_files(db_session, fake_storage_gateway, sample_project, sample_user):
    """Crea archivos de input y product, y los precarga en el storage."""
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
            input_file_storage_path=f"users/u91/projects/{proj_id}/input/in_{i}.txt",
            input_file_type=FileType.txt,
            input_file_size_bytes=len(f"input-{i}".encode()),
            input_file_storage_backend=StorageBackend.supabase,
            input_file_is_active=True,
            input_file_is_archived=False,
        )
        for i in range(2)
    ]
    products = [
        ProductFile(
            product_file_id=uuid4(),
            project_id=proj_id,
            product_file_generated_by=user_uuid,
            product_file_original_name=f"out_{i}.pdf",
            product_file_display_name=f"out_{i}.pdf",
            product_file_mime_type="application/pdf",
            product_file_storage_path=f"users/u91/projects/{proj_id}/output/out_{i}.pdf",
            product_file_type=ProductFileType.document,
            product_file_version=ProductVersion.v1,
            product_file_size_bytes=len(f"out-{i}".encode()),
            product_file_storage_backend=StorageBackend.supabase,
            product_file_is_active=True,
            product_file_is_archived=False,
        )
        for i in range(2)
    ]
    for f in inputs + products:
        db_session.add(f)
        fake_storage_gateway.preload(
            f.input_file_storage_path if hasattr(f, 'input_file_storage_path') else f.product_file_storage_path,
            (f.input_file_display_name if hasattr(f, 'input_file_display_name') else f.product_file_display_name).encode()
        )
    await db_session.commit()
    return inputs, products


@pytest.fixture
def fake_project_service():
    """Simula servicio de validación de permisos de proyectos."""
    class FakeAccess:
        async def validate_user_access(self, project_id: int, user_id: str):
            if project_id == 999:
                raise PermissionError("Acceso denegado")
            return True
    return FakeAccess()


@pytest.mark.asyncio
async def test_bulk_download_happy_path_creates_zip(db_session, seed_files, fake_storage_gateway, fake_project_service, sample_project, sample_user):
    """
    Debe generar un ZIP con múltiples archivos del proyecto.
    """
    svc = BulkDownloadService(db=db_session, storage=fake_storage_gateway, project_service=fake_project_service)
    user_id = sample_user.user_id
    project_id = sample_project.project_id

    zip_bytes = await svc.create_bulk_download(project_id=project_id, user_id=user_id)

    assert isinstance(zip_bytes, (bytes, bytearray))
    assert len(zip_bytes) > 100, "El ZIP debe contener archivos concatenados"

    # Verificar estructura interna del ZIP
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert any(n.startswith("input/") for n in names)
        assert any(n.startswith("output/") for n in names)


@pytest.mark.asyncio
async def test_bulk_download_permission_denied_raises(db_session, fake_storage_gateway, fake_project_service):
    """
    Si el usuario no tiene acceso al proyecto, debe lanzar PermissionError.
    """
    svc = BulkDownloadService(db=db_session, storage=fake_storage_gateway, project_service=fake_project_service)
    with pytest.raises(PermissionError):
        await svc.create_bulk_download(project_id=999, user_id="u_denied")


@pytest.mark.asyncio
async def test_bulk_download_filters_by_category(db_session, seed_files, fake_storage_gateway, fake_project_service, sample_project, sample_user):
    """
    Debe permitir generar el ZIP solo con una categoría específica.
    """
    svc = BulkDownloadService(db=db_session, storage=fake_storage_gateway, project_service=fake_project_service)
    user_id = sample_user.user_id
    project_id = sample_project.project_id

    zip_bytes = await svc.create_bulk_download(project_id=project_id, user_id=user_id, category=FileCategory.input)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert all(n.startswith("input/") for n in names)


@pytest.mark.asyncio
async def test_bulk_download_empty_project_returns_empty_zip(db_session, fake_storage_gateway, fake_project_service):
    """
    Si el proyecto no tiene archivos, debe devolver ZIP vacío válido.
    """
    svc = BulkDownloadService(db=db_session, storage=fake_storage_gateway, project_service=fake_project_service)
    user_id = "usr_ok"
    project_id = 12345

    zip_bytes = await svc.create_bulk_download(project_id=project_id, user_id=user_id)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        assert zf.namelist() == []


@pytest.mark.asyncio
async def test_bulk_download_handles_missing_files_gracefully(db_session, seed_files, fake_storage_gateway, fake_project_service, sample_project, sample_user):
    """
    Si un archivo del proyecto no existe en storage, debe continuar con los demás.
    """
    inputs, products = seed_files
    # Elimina el primer input del storage simulado usando su path real
    first_input_path = inputs[0].input_file_storage_path
    if first_input_path in fake_storage_gateway.files:
        del fake_storage_gateway.files[first_input_path]

    svc = BulkDownloadService(db=db_session, storage=fake_storage_gateway, project_service=fake_project_service)
    user_id = sample_user.user_id
    project_id = sample_project.project_id

    zip_bytes = await svc.create_bulk_download(project_id=project_id, user_id=user_id)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert "input/in_0.txt" not in names
        assert any("output/" in n for n in names)


# Fin del archivo tests/modules/files/services/downloads/test_bulk_download_service.py

