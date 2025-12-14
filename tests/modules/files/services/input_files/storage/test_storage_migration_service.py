
# tests/modules/files/services/input_files/storage/test_storage_migration_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio StorageMigrationService del módulo Files.

Cubre:
- Migración exitosa de archivo entre distintos StorageBackend.
- Validación de contenido transferido.
- Detección de errores en backends de destino y rollback.
- Verificación de actualización en BD.
- Manejo de archivos inexistentes.
"""

import pytest
from unittest.mock import AsyncMock

from app.modules.files.enums import StorageBackend
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.services.storage.storage_migration_service import StorageMigrationService


@pytest.fixture
def fake_gateways(tmp_path):
    """Crea gateways simulados para origen y destino."""
    class FakeGateway:
        def __init__(self, name, root):
            self.name = name
            self.root = root
            self.files = {}

        async def download(self, path):
            if path not in self.files:
                raise FileNotFoundError(f"[{self.name}] no encontrado: {path}")
            return self.files[path]

        async def upload(self, path, data):
            self.files[path] = data
            return {"path": path, "backend": self.name}

        async def delete(self, path):
            if path in self.files:
                del self.files[path]
            return True

    src = FakeGateway("local", tmp_path)
    dst = FakeGateway("s3", tmp_path / "s3")
    return src, dst


@pytest.mark.asyncio
async def test_migrate_file_success_updates_backend_and_path(db_session, fake_gateways):
    """
    Debe migrar un archivo exitosamente a otro backend y actualizar en BD.
    """
    src, dst = fake_gateways
    from uuid import uuid4, UUID
    from app.modules.files.enums import FileType
    
    user_uuid = UUID(int=1)
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="input.csv",
        input_file_display_name="input.csv",
        input_file_mime_type="text/csv",
        input_file_type=FileType.csv,
        input_file_size_bytes=100,
        input_file_storage_path="users/u1/projects/1/input/input.csv",
        input_file_storage_backend=StorageBackend.supabase,
    )
    db_session.add(file)
    await db_session.flush()
    
    file_id = file.input_file_id

    # Contenido simulado
    src.files[file.input_file_storage_path] = b"CSV,data,values"

    svc = StorageMigrationService(db=db_session, src_gateway=src, dst_gateway=dst)
    result = await svc.migrate_file(file_id=file_id, new_backend=StorageBackend.s3)

    # Assert: backend actualizado
    assert result.input_file_storage_backend == StorageBackend.s3
    assert file.input_file_storage_path in dst.files
    assert dst.files[file.input_file_storage_path] == b"CSV,data,values"
    # Origen borrado
    assert file.input_file_storage_path not in src.files


@pytest.mark.asyncio
async def test_migrate_file_nonexistent_source_raises(db_session, fake_gateways):
    """
    Si el archivo no existe en el backend de origen, debe lanzar FileNotFoundError.
    """
    src, dst = fake_gateways
    from uuid import uuid4, UUID
    from app.modules.files.enums import FileType
    
    user_uuid = UUID(int=1)
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="missing.txt",
        input_file_display_name="missing.txt",
        input_file_mime_type="text/plain",
        input_file_type=FileType.txt,
        input_file_size_bytes=100,
        input_file_storage_path="users/u2/projects/2/input/missing.txt",
        input_file_storage_backend=StorageBackend.supabase,
    )
    db_session.add(file)
    await db_session.flush()
    
    file_id = file.input_file_id

    svc = StorageMigrationService(db=db_session, src_gateway=src, dst_gateway=dst)

    with pytest.raises(FileNotFoundError):
        await svc.migrate_file(file_id=file_id, new_backend=StorageBackend.s3)


@pytest.mark.asyncio
async def test_migrate_file_upload_failure_rolls_back(db_session, fake_gateways, monkeypatch):
    """
    Si falla la subida al backend destino, debe revertir cualquier cambio.
    """
    src, dst = fake_gateways
    from uuid import uuid4, UUID
    from app.modules.files.enums import FileType
    
    user_uuid = UUID(int=1)
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="roll.txt",
        input_file_display_name="roll.txt",
        input_file_mime_type="text/plain",
        input_file_type=FileType.txt,
        input_file_size_bytes=100,
        input_file_storage_path="users/u3/projects/3/input/roll.txt",
        input_file_storage_backend=StorageBackend.supabase,
    )
    db_session.add(file)
    await db_session.flush()
    
    file_id = file.input_file_id

    src.files[file.input_file_storage_path] = b"rollback-test"

    async def fail_upload(path, data):
        raise IOError("Simulated upload failure")

    monkeypatch.setattr(dst, "upload", fail_upload)

    svc = StorageMigrationService(db=db_session, src_gateway=src, dst_gateway=dst)

    with pytest.raises(IOError):
        await svc.migrate_file(file_id=file_id, new_backend=StorageBackend.s3)

    # Verifica que el archivo siga en origen
    assert file.input_file_storage_path in src.files
    # BD no actualizó backend
    assert file.input_file_storage_backend == StorageBackend.supabase


@pytest.mark.asyncio
async def test_migrate_file_keeps_metadata_intact(db_session, fake_gateways):
    """
    La migración no debe alterar metadatos como tamaño, nombre o checksum.
    """
    src, dst = fake_gateways
    from uuid import uuid4, UUID
    from app.modules.files.enums import FileType
    
    user_uuid = UUID(int=1)
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="meta.docx",
        input_file_display_name="meta.docx",
        input_file_mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        input_file_type=FileType.docx,
        input_file_storage_path="users/u3/projects/3/input/meta.docx",
        input_file_storage_backend=StorageBackend.supabase,
        input_file_size_bytes=128,
    )
    db_session.add(file)
    await db_session.flush()
    
    file_id = file.input_file_id

    src.files[file.input_file_storage_path] = b"x" * 128

    svc = StorageMigrationService(db=db_session, src_gateway=src, dst_gateway=dst)
    result = await svc.migrate_file(file_id=file_id, new_backend=StorageBackend.s3)

    assert result.input_file_display_name == "meta.docx"
    assert result.input_file_size_bytes == 128
    assert result.input_file_storage_backend == StorageBackend.s3


@pytest.mark.asyncio
async def test_migrate_file_invalid_backend_raises_valueerror(db_session, fake_gateways):
    """
    Si se pasa un backend inválido, debe lanzar ValueError.
    """
    src, dst = fake_gateways
    from uuid import uuid4, UUID
    from app.modules.files.enums import FileType
    
    user_uuid = UUID(int=1)
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="backend_fail.txt",
        input_file_display_name="backend_fail.txt",
        input_file_mime_type="text/plain",
        input_file_type=FileType.txt,
        input_file_size_bytes=100,
        input_file_storage_path="users/u3/projects/3/input/backend_fail.txt",
        input_file_storage_backend=StorageBackend.supabase,
    )
    db_session.add(file)
    await db_session.flush()
    
    file_id = file.input_file_id

    svc = StorageMigrationService(db=db_session, src_gateway=src, dst_gateway=dst)
    with pytest.raises(ValueError):
        await svc.migrate_file(file_id=file_id, new_backend="nube_falsa")


# Fin del archivo tests/modules/files/services/input_files/storage/test_storage_migration_service.py
