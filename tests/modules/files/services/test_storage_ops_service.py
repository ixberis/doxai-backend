
# tests/modules/files/services/test_storage_ops_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio StorageOpsService del módulo Files.

Cubre:
- Listado de archivos de un proyecto usando storage_gateway simulado.
- Eliminación segura de archivos.
- Copia y movimiento entre rutas válidas.
- Validación de rutas seguras (sin traversal).
- Manejo de errores de gateway (FileNotFoundError, PermissionError).
"""

import pytest
from typing import Optional
from unittest.mock import AsyncMock

from app.modules.files.services.storage_ops_service import StorageOpsService


@pytest.fixture
def fake_gateway(tmp_path):
    """Simula un gateway de almacenamiento con operaciones básicas."""
    class FakeGateway:
        def __init__(self):
            self.files = {"a.txt": b"A", "b.txt": b"B"}
            self.deleted = set()
            self.moved = []

        async def list(self, path: str, recursive: bool = False, prefix: Optional[str] = None, suffix: Optional[str] = None):
            """List files with optional prefix filter."""
            base = prefix if prefix else path
            return [{"path": k, "size": len(v)} for k, v in self.files.items() if k.startswith(base)]

        async def delete(self, path: str):
            if path not in self.files:
                raise FileNotFoundError(path)
            self.deleted.add(path)
            del self.files[path]
            return True

        async def move(self, src: str, dest: str):
            if src not in self.files:
                raise FileNotFoundError(src)
            if "../" in dest or dest.startswith("/"):
                raise ValueError("Invalid path")
            self.files[dest] = self.files.pop(src)
            self.moved.append((src, dest))
            return True

    return FakeGateway()


@pytest.mark.asyncio
async def test_list_files_returns_expected_entries(fake_gateway):
    """
    Debe listar correctamente archivos bajo un prefijo dado.
    """
    svc = StorageOpsService(storage=fake_gateway)
    files = await svc.list_files(path="")
    assert isinstance(files, list)
    assert {"a.txt", "b.txt"} == {f["path"] for f in files}


@pytest.mark.asyncio
async def test_delete_file_removes_entry(fake_gateway):
    """
    Debe eliminar archivo existente y registrar operación.
    """
    svc = StorageOpsService(storage=fake_gateway)
    await svc.delete_file("a.txt")
    assert "a.txt" in fake_gateway.deleted
    assert "a.txt" not in fake_gateway.files


@pytest.mark.asyncio
async def test_delete_file_missing_raises(fake_gateway):
    """
    Eliminar archivo inexistente debe lanzar FileNotFoundError.
    """
    svc = StorageOpsService(storage=fake_gateway)
    with pytest.raises(FileNotFoundError):
        await svc.delete_file("nope.txt")


@pytest.mark.asyncio
async def test_move_file_updates_storage(fake_gateway):
    """
    Debe mover archivo correctamente a nueva ruta válida.
    """
    svc = StorageOpsService(storage=fake_gateway)
    await svc.move_file("b.txt", "folder/new_b.txt")
    assert ("b.txt", "folder/new_b.txt") in fake_gateway.moved
    assert "folder/new_b.txt" in fake_gateway.files
    assert "b.txt" not in fake_gateway.files


@pytest.mark.asyncio
async def test_move_file_invalid_path_raises(fake_gateway):
    """
    Debe rechazar rutas inseguras.
    """
    svc = StorageOpsService(storage=fake_gateway)
    with pytest.raises(ValueError):
        await svc.move_file("a.txt", "../hack.txt")


@pytest.mark.asyncio
async def test_gateway_error_is_propagated(fake_gateway, monkeypatch):
    """
    Debe propagar errores inesperados del gateway.
    """
    svc = StorageOpsService(storage=fake_gateway)
    async def fail_list(path, **kwargs): raise PermissionError("Denied")
    monkeypatch.setattr(fake_gateway, "list", fail_list)
    with pytest.raises(PermissionError):
        await svc.list_files(path="")

# Fin del archivo tests/modules/files/services/test_storage_ops_service.py
