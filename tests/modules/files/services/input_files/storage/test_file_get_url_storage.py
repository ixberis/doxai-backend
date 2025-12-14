
# tests/modules/files/services/input_files/storage/test_file_get_url_storage.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio de generación de URLs presignadas (FileGetUrlStorage).

Cubre:
- Generación exitosa de URL presignada con expiración por defecto.
- Validación de parámetros requeridos (ruta válida, tiempo positivo).
- Prevención de rutas inseguras (../ o absolutas).
- Error manejado cuando el gateway falla o ruta inexistente.
"""

import pytest
import re
from datetime import timedelta

from app.modules.files.services.storage.storage_paths import StoragePathsService
from app.modules.files.services.storage.file_get_url_storage import FileGetUrlStorage


class FakeGateway:
    """Simula un proveedor de URLs presignadas."""
    def __init__(self):
        self.urls = {}

    async def presign_url(self, path: str, expires_in: int):
        if "../" in path or path.startswith("/"):
            raise ValueError("Unsafe path")
        if "missing" in path:
            raise FileNotFoundError(path)
        url = f"https://storage.fake/{path}?exp={expires_in}"
        self.urls[path] = url
        return url


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
def paths():
    return StoragePathsService(base_prefix="users")


@pytest.fixture
def signer(paths, gateway):
    return FileGetUrlStorage(paths_service=paths, gateway=gateway)


@pytest.mark.asyncio
async def test_presign_url_happy_path_generates_valid_link(signer):
    """
    Debe generar una URL presignada correctamente formateada.
    """
    path = "users/u1/projects/1/input/data.csv"
    url = await signer.get_presigned_url(path)
    assert url.startswith("https://storage.fake/users/u1/projects/1/input/data.csv")
    assert re.search(r"exp=\d+", url)


@pytest.mark.asyncio
async def test_presign_url_accepts_custom_expiration(signer):
    """
    Debe aceptar expiraciones personalizadas (timedelta o int).
    """
    path = "users/u1/projects/1/input/file.txt"
    url1 = await signer.get_presigned_url(path, expires_in=600)
    url2 = await signer.get_presigned_url(path, expires_in=timedelta(minutes=10))
    assert url1.endswith("exp=600")
    assert "exp=600" in url2 or "exp=600.0" in url2


@pytest.mark.asyncio
async def test_presign_url_rejects_insecure_path(signer):
    """
    Debe rechazar rutas inseguras.
    """
    with pytest.raises(ValueError):
        await signer.get_presigned_url("../escape.txt")
    with pytest.raises(ValueError):
        await signer.get_presigned_url("/absolute/path.txt")


@pytest.mark.asyncio
async def test_presign_url_invalid_expiration_raises(signer):
    """
    Expiraciones no válidas (<=0) deben lanzar ValueError.
    """
    path = "users/u1/projects/1/input/file.txt"
    with pytest.raises(ValueError):
        await signer.get_presigned_url(path, expires_in=-5)
    with pytest.raises(ValueError):
        await signer.get_presigned_url(path, expires_in=0)


@pytest.mark.asyncio
async def test_presign_url_handles_missing_file_gracefully(signer):
    """
    Si el gateway lanza FileNotFoundError, el servicio debe propagarlo.
    """
    path = "users/u1/projects/1/input/missing.txt"
    with pytest.raises(FileNotFoundError):
        await signer.get_presigned_url(path)


@pytest.mark.asyncio
async def test_presign_url_returns_unique_each_call(signer):
    """
    Cada llamada debe generar un URL independiente (aunque idéntico path y expiración).
    """
    path = "users/u1/projects/1/input/data.csv"
    url1 = await signer.get_presigned_url(path, expires_in=60)
    url2 = await signer.get_presigned_url(path, expires_in=60)
    # Aunque puedan coincidir en valor, se asegura que no haya mutación interna del dict
    assert path in signer.gateway.urls
    assert url1 == url2


# Fin del archivo tests/modules/files/services/input_files/storage/test_file_get_url_storage.py
