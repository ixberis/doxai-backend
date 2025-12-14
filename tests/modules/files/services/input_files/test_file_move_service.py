
# tests/modules/files/services/input_files/test_file_move_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio FileMoveService del módulo Files.

Cubre:
- Movimiento exitoso de archivo a nueva ruta.
- Prevención de colisiones (ruta ya existente).
- Actualización del registro en base de datos.
- Manejo de rollback si ocurre un fallo durante la operación.
- Interacción correcta con el gateway de almacenamiento.
"""

import pytest
from unittest.mock import AsyncMock

from app.modules.files.facades.errors import StoragePathCollision
from app.modules.files.enums import StorageBackend
from app.modules.files.models.input_file_models import InputFile
from app.modules.files.services.file_move_service import FileMoveService


@pytest.fixture
def fake_storage_gateway(tmp_path):
    """Gateway simulado de almacenamiento para operaciones de move."""
    class FakeStorageGateway:
        def __init__(self, root):
            self.root = root
            self.files = {}

        async def exists(self, path):
            return path in self.files

        async def move(self, src, dest):
            if dest in self.files:
                raise StoragePathCollision(f"Destino ya existente: {dest}")
            if src not in self.files:
                raise FileNotFoundError(f"No existe el archivo fuente: {src}")
            self.files[dest] = self.files.pop(src)
            return {"from": src, "to": dest}

        async def upload(self, path, data: bytes):
            self.files[path] = len(data)

    gw = FakeStorageGateway(tmp_path)
    return gw


@pytest.mark.asyncio
async def test_move_file_happy_path_updates_db_and_storage(db_session, fake_storage_gateway):
    """
    Debe mover correctamente un archivo y actualizar la ruta en la base de datos.
    """
    # Arrange
    from uuid import uuid4
    from app.modules.files.enums import FileType
    
    user_uuid = uuid4()  # UUID real para evitar problemas de conversión
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="old.txt",
        input_file_display_name="old.txt",
        input_file_mime_type="text/plain",
        input_file_type=FileType.txt,
        input_file_size_bytes=42,
        input_file_storage_path="old.txt",
        input_file_storage_backend=StorageBackend.supabase
    )
    db_session.add(file)
    await db_session.flush()
    
    file_id = file.input_file_id

    fake_storage_gateway.files["old.txt"] = 42

    service = FileMoveService(db=db_session, storage=fake_storage_gateway)

    # Act
    result = await service.move_file(file_id=file_id, new_path="folder/new.txt")

    # Assert
    assert result.input_file_storage_path == "folder/new.txt"
    assert "folder/new.txt" in fake_storage_gateway.files
    assert "old.txt" not in fake_storage_gateway.files


@pytest.mark.asyncio
async def test_move_file_detects_collision_and_raises(db_session, fake_storage_gateway):
    """
    No debe permitir mover un archivo a una ruta ya existente.
    """
    from uuid import uuid4
    from app.modules.files.enums import FileType
    
    user_uuid = uuid4()
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="doc.txt",
        input_file_display_name="doc.txt",
        input_file_mime_type="text/plain",
        input_file_type=FileType.txt,
        input_file_size_bytes=10,
        input_file_storage_path="doc.txt",
        input_file_storage_backend=StorageBackend.supabase
    )
    db_session.add(file)
    await db_session.flush()
    
    file_id = file.input_file_id

    fake_storage_gateway.files["doc.txt"] = 10
    fake_storage_gateway.files["target.txt"] = 20  # colisión simulada

    service = FileMoveService(db=db_session, storage=fake_storage_gateway)

    with pytest.raises(StoragePathCollision):
        await service.move_file(file_id=file_id, new_path="target.txt")


@pytest.mark.asyncio
async def test_move_file_rolls_back_on_storage_failure(db_session, fake_storage_gateway, monkeypatch):
    """
    Si falla el movimiento en storage, debe revertir el cambio en la BD.
    """
    from uuid import uuid4
    from app.modules.files.enums import FileType
    
    user_uuid = uuid4()
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="data.txt",
        input_file_display_name="data.txt",
        input_file_mime_type="text/plain",
        input_file_type=FileType.txt,
        input_file_size_bytes=123,
        input_file_storage_path="data.txt",
        input_file_storage_backend=StorageBackend.supabase
    )
    db_session.add(file)
    await db_session.commit()  # Commit para persistir antes del test
    
    file_id = file.input_file_id

    fake_storage_gateway.files["data.txt"] = 123

    service = FileMoveService(db=db_session, storage=fake_storage_gateway)

    async def fail_move(src, dest):
        raise IOError("Simulated I/O failure")

    monkeypatch.setattr(fake_storage_gateway, "move", fail_move)

    with pytest.raises(IOError):
        await service.move_file(file_id=file_id, new_path="failed.txt")

    # La ruta en BD debe mantenerse igual
    updated = await db_session.get(InputFile, file_id)
    assert updated.input_file_storage_path == "data.txt"


@pytest.mark.asyncio
async def test_move_nonexistent_file_raises_valueerror(db_session, fake_storage_gateway):
    """
    Si el archivo no existe en BD, debe lanzar ValueError.
    """
    from uuid import uuid4
    service = FileMoveService(db=db_session, storage=fake_storage_gateway)
    with pytest.raises(ValueError):
        await service.move_file(file_id=uuid4(), new_path="nope.txt")


@pytest.mark.asyncio
async def test_move_file_invalid_target_path(db_session, fake_storage_gateway):
    """
    Si el nuevo path es inválido o inseguro, debe lanzar ValueError.
    """
    from uuid import uuid4
    from app.modules.files.enums import FileType
    
    user_uuid = uuid4()
    
    file = InputFile(
        input_file_id=uuid4(),
        project_id=uuid4(),
        input_file_uploaded_by=user_uuid,
        input_file_original_name="a.txt",
        input_file_display_name="a.txt",
        input_file_mime_type="text/plain",
        input_file_type=FileType.txt,
        input_file_size_bytes=5,
        input_file_storage_path="a.txt",
        input_file_storage_backend=StorageBackend.supabase
    )
    db_session.add(file)
    await db_session.flush()
    
    file_id = file.input_file_id

    service = FileMoveService(db=db_session, storage=fake_storage_gateway)

    with pytest.raises(ValueError):
        await service.move_file(file_id=file_id, new_path="../evil.txt")


# Fin del archivo tests/modules/files/services/input_files/test_file_move_service.py