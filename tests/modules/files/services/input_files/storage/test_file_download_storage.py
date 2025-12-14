
# tests/modules/files/services/input_files/storage/test_file_download_storage.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio de descarga de archivos (FileDownloadStorage).

Cubre:
- Descarga exitosa (retorna bytes idénticos).
- Manejo de archivos inexistentes (FileNotFoundError).
- Validación de path seguro.
- Descarga mediante stream (cuando la API lo soporta).
- Retorno de tamaño y metadatos.
"""

import io
import pytest

from app.modules.files.services.storage.storage_paths import StoragePathsService
from app.modules.files.services.storage.file_download_storage import FileDownloadStorage


class FakeGateway:
    """Gateway simulado para operaciones de descarga."""
    def __init__(self):
        self._files = {}

    async def exists(self, path: str) -> bool:
        return path in self._files

    async def download(self, path: str) -> bytes:
        if path not in self._files:
            raise FileNotFoundError(path)
        return self._files[path]

    async def download_stream(self, path: str):
        if path not in self._files:
            raise FileNotFoundError(path)
        return io.BytesIO(self._files[path])


@pytest.fixture
def gateway():
    g = FakeGateway()
    g._files["users/u1/projects/1/input/sample.txt"] = b"Hola mundo"
    g._files["users/u2/projects/2/input/big.bin"] = b"x" * 4096
    return g


@pytest.fixture
def paths():
    return StoragePathsService(base_prefix="users")


@pytest.fixture
def downloader(paths, gateway):
    return FileDownloadStorage(paths_service=paths, gateway=gateway)


@pytest.mark.asyncio
async def test_download_happy_path_returns_bytes(downloader):
    """
    Debe descargar correctamente los bytes del archivo solicitado.
    """
    path = "users/u1/projects/1/input/sample.txt"
    data = await downloader.download(path)
    assert isinstance(data, bytes)
    assert data == b"Hola mundo"


@pytest.mark.asyncio
async def test_download_nonexistent_raises_notfound(downloader):
    """
    Debe lanzar FileNotFoundError si el archivo no existe.
    """
    with pytest.raises(FileNotFoundError):
        await downloader.download("users/u9/projects/9/input/missing.txt")


@pytest.mark.asyncio
async def test_download_stream_mode_returns_stream(downloader):
    """
    Debe devolver un stream file-like cuando se solicita modo stream.
    """
    path = "users/u2/projects/2/input/big.bin"
    stream = await downloader.download_stream(path)
    content = await stream.read()
    assert len(content) == 4096
    assert content.startswith(b"x")
    assert hasattr(stream, "read")


@pytest.mark.asyncio
async def test_download_rejects_insecure_paths(downloader):
    """
    No debe permitir rutas inseguras (../ o absolutas).
    """
    with pytest.raises(ValueError):
        await downloader.download("../escape.txt")
    with pytest.raises(ValueError):
        await downloader.download("/absolute/path.txt")


@pytest.mark.asyncio
async def test_download_returns_size_and_metadata(downloader):
    """
    Debe proporcionar metadata adicional (size) cuando se solicita.
    """
    path = "users/u1/projects/1/input/sample.txt"
    result = await downloader.download_with_metadata(path)
    assert isinstance(result, dict)
    assert result["path"] == path
    assert result["size"] == len(b"Hola mundo")
    assert result["bytes"].startswith(b"Hola")


# Fin del archivo tests/modules/files/services/input_files/storage/test_file_download_storage.py
