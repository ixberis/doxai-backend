
# tests/modules/files/services/input_files/storage/test_file_upload_storage.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio de subida a storage (FileUploadStorage).

Cubre:
- Subida exitosa con cálculo de ruta vía StoragePathsService.
- Prevención de colisiones (exists -> StoragePathCollision).
- Rechazo de nombres/rutas inseguros.
- Retorno de metadatos (path, size, mime_type) coherentes.
- Preserva bytes exactamente (verificación leída desde el gateway fake).
"""

import io
import os
import pytest

from app.modules.files.facades.errors import StoragePathCollision
from app.modules.files.services.storage.storage_paths import StoragePathsService
from app.modules.files.services.storage.file_upload_storage import FileUploadStorage


class FakeGateway:
    """Gateway de almacenamiento simulado (subconjunto de interfaz)."""
    def __init__(self):
        # path -> bytes
        self._blobs = {}

    async def exists(self, path: str) -> bool:
        return path in self._blobs

    async def upload(self, path: str, data: bytes, *, content_type: str | None = None):
        if path in self._blobs:
            raise StoragePathCollision(f"Ruta ya existente: {path}")
        self._blobs[path] = data
        # Simula respuesta de un proveedor de storage
        return {
            "path": path,
            "size": len(data),
            "content_type": content_type,
        }

    async def download(self, path: str) -> bytes:
        if path not in self._blobs:
            raise FileNotFoundError(path)
        return self._blobs[path]


@pytest.fixture
def paths():
    # Base en bucket "users" tal como está definido en el módulo Files
    return StoragePathsService(base_prefix="users")


@pytest.fixture
def gw():
    return FakeGateway()


@pytest.fixture
def uploader(paths, gw):
    # SUT
    return FileUploadStorage(paths_service=paths, gateway=gw)


@pytest.mark.asyncio
async def test_upload_happy_path_builds_safe_path_and_stores_bytes(uploader, gw):
    """
    Debe construir ruta segura y subir bytes íntegros al gateway.
    """
    user_id = "u1"
    project_id = 101
    file_name = "reporte.pdf"
    data = b"%PDF-1.7 DoxAI\n..."

    result = await uploader.upload_input_file(
        user_id=user_id,
        project_id=project_id,
        file_name=file_name,
        data=data,
        content_type="application/pdf",
    )

    # Verifica ruta construida y metadatos retornados
    expected_path = f"users/{user_id}/projects/{project_id}/input/{file_name}"
    assert result.path == expected_path
    assert result.size == len(data)
    assert result.content_type == "application/pdf"

    # Verifica bytes preservados en storage
    stored = await gw.download(expected_path)
    assert stored == data


@pytest.mark.asyncio
async def test_upload_detects_collision_and_raises(uploader, gw):
    """
    Si exists(path) == True, debe lanzar StoragePathCollision.
    """
    user_id = "u2"
    project_id = 202
    file_name = "duplicado.csv"
    data = b"a,b,c\n1,2,3\n"

    # Primera subida OK
    await uploader.upload_input_file(
        user_id=user_id,
        project_id=project_id,
        file_name=file_name,
        data=data,
        content_type="text/csv",
    )

    # Intento duplicado
    with pytest.raises(StoragePathCollision):
        await uploader.upload_input_file(
            user_id=user_id,
            project_id=project_id,
            file_name=file_name,
            data=data,
            content_type="text/csv",
        )


@pytest.mark.asyncio
async def test_upload_rejects_unsafe_filename(uploader):
    """
    Debe rechazar nombres inseguros (traversal o separadores inválidos).
    """
    with pytest.raises(ValueError):
        await uploader.upload_input_file(
            user_id="u3",
            project_id=303,
            file_name="../hack.sh",
            data=b"#!/bin/sh",
            content_type="text/x-sh",
        )

    with pytest.raises(ValueError):
        await uploader.upload_input_file(
            user_id="u3",
            project_id=303,
            file_name="bad\\name.txt",
            data=b"oops",
            content_type="text/plain",
        )


@pytest.mark.asyncio
async def test_upload_accepts_zero_byte_and_sets_metadata(uploader, gw):
    """
    Debe aceptar archivo vacío y devolver metadatos coherentes.
    """
    result = await uploader.upload_input_file(
        user_id="u4",
        project_id=404,
        file_name="empty.log",
        data=b"",
        content_type="text/plain",
    )

    assert result.size == 0
    assert result.content_type == "text/plain"
    stored = await gw.download(result.path)
    assert stored == b""


@pytest.mark.asyncio
async def test_upload_supports_bytes_and_stream(uploader, gw):
    """
    Debe soportar tanto bytes como streams file-like.
    """
    user_id = "u5"
    project_id = 505
    file_name = "from_stream.bin"
    buf = io.BytesIO(os.urandom(2048))

    result = await uploader.upload_input_file(
        user_id=user_id,
        project_id=project_id,
        file_name=file_name,
        data=buf,  # stream
        content_type="application/octet-stream",
    )

    assert result.size == 2048
    stored = await gw.download(result.path)
    assert len(stored) == 2048


# Fin del archivo tests/modules/files/services/input_files/storage/test_file_upload_storage.py
