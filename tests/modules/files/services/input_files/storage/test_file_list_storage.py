
# tests/modules/files/services/input_files/storage/test_file_list_storage.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio de listado en storage (FileListStorage).

Cubre:
- Listado básico de una carpeta (no recursivo).
- Listado recursivo (si el servicio lo soporta).
- Filtros por prefijo/sufijo (contrato laxo: si no existen, se ignoran sin romper).
- Paginación (limit/next_token) con contrato laxo (acepta dict o lista).
- Validación de rutas seguras (rechazo de traversal/absolutas).
"""

import pytest
from typing import Iterable

from app.modules.files.services.storage.storage_paths import StoragePathsService
from app.modules.files.services.storage.file_list_storage import FileListStorage


class FakeGateway:
    """
    Gateway simulado para listado.
    Representa un 'bucket' en un dict path->is_dir|bytes.
    """
    def __init__(self):
        # True => directorio lógico; bytes => archivo
        self._fs = {}

    def _ensure_dir(self, path: str):
        path = path.rstrip("/") + "/"
        self._fs[path] = True

    def _put_file(self, path: str, data: bytes = b"x"):
        self._fs[path] = data

    async def list(self, base: str, *, recursive: bool = False) -> Iterable[dict]:
        """
        Devuelve elementos bajo 'base'. Cada item:
        { 'path': <str>, 'is_dir': <bool>, 'size': <int | None> }
        """
        base = base.rstrip("/") + "/"
        results = []
        for p, v in self._fs.items():
            if not p.startswith(base):
                continue
            # No recursivo: sólo hijos directos
            if not recursive:
                # Acepta: base/foo, base/bar.txt pero no base/foo/sub/file
                rel = p[len(base):]
                if "/" in rel.strip("/"):
                    # Tiene más de un nivel: sólo mantén el primer directorio
                    first = rel.split("/", 1)[0]
                    # Representa el directorio directo
                    results.append({"path": base + first + "/", "is_dir": True, "size": None})
                    continue
            if v is True:  # dir
                results.append({"path": p if p.endswith("/") else p + "/", "is_dir": True, "size": None})
            else:
                results.append({"path": p, "is_dir": False, "size": len(v)})
        # Normaliza duplicados (por agregación de directorios no recursiva)
        uniq = {(i["path"], i["is_dir"]): i for i in results}
        return list(uniq.values())


@pytest.fixture
def paths():
    return StoragePathsService(base_prefix="users")


@pytest.fixture
def gateway():
    g = FakeGateway()
    # Estructura simulada
    g._ensure_dir("users/u1/projects/1/input")
    g._ensure_dir("users/u1/projects/1/input/docs")
    g._ensure_dir("users/u1/projects/1/input/data")
    g._put_file("users/u1/projects/1/input/README.txt", b"hola")
    g._put_file("users/u1/projects/1/input/docs/a.pdf", b"%PDF")
    g._put_file("users/u1/projects/1/input/docs/b.pdf", b"%PDF")
    g._put_file("users/u1/projects/1/input/data/table.csv", b"a,b,c\n1,2,3\n")
    g._put_file("users/u1/projects/1/input/data/dump.json", b"{}")
    return g


@pytest.fixture
def lister(paths, gateway):
    return FileListStorage(paths_service=paths, gateway=gateway)


def _unwrap_items(result):
    """
    Admite dos contratos posibles:
      - lista directa de items
      - dict con 'items' y opcionalmente 'next_token'
    """
    if isinstance(result, dict) and "items" in result:
        return result["items"]
    assert isinstance(result, list)
    return result


@pytest.mark.asyncio
async def test_list_folder_basic_non_recursive(lister):
    """
    Debe listar sólo hijos directos cuando recursive=False.
    """
    base = "users/u1/projects/1/input/"
    result = await lister.list_folder(base, recursive=False)
    items = _unwrap_items(result)

    paths = {i["path"] for i in items}
    # Debe ver README.txt y las carpetas docs/ y data/ como hijos directos
    assert f"{base}README.txt" in paths
    assert f"{base}docs/" in paths
    assert f"{base}data/" in paths
    # No debe listar nietos directos (p.ej. docs/a.pdf) en modo no recursivo
    assert f"{base}docs/a.pdf" not in paths


@pytest.mark.asyncio
async def test_list_folder_recursive_sees_nested_files(lister):
    """
    Debe listar los archivos anidados cuando recursive=True (si la implementación lo soporta).
    """
    base = "users/u1/projects/1/input/"
    result = await lister.list_folder(base, recursive=True)
    items = _unwrap_items(result)
    paths = {i["path"] for i in items}
    assert f"{base}docs/a.pdf" in paths
    assert f"{base}docs/b.pdf" in paths
    assert f"{base}data/table.csv" in paths
    assert f"{base}data/dump.json" in paths


@pytest.mark.asyncio
async def test_list_folder_filters_by_suffix_and_prefix(lister):
    """
    Debe aplicar filtros por sufijo y prefijo (contrato laxo: si no existen, se ignoran).
    """
    base = "users/u1/projects/1/input/"

    # Filtra por sufijo .pdf
    res_pdf = await lister.list_folder(base, recursive=True, suffix=".pdf")
    items_pdf = _unwrap_items(res_pdf)
    assert all(it["path"].endswith(".pdf") for it in items_pdf)
    assert len(items_pdf) >= 2

    # Filtra por prefijo 'data/'
    res_data = await lister.list_folder(base, recursive=True, prefix="data/")
    items_data = _unwrap_items(res_data)
    assert all("/input/data/" in it["path"] for it in items_data)
    assert any(it["path"].endswith("table.csv") for it in items_data)


@pytest.mark.asyncio
async def test_list_folder_pagination_contract_is_lax(lister):
    """
    Si el servicio soporta limit/next_token debe paginar; de lo contrario,
    al menos debe devolver la colección completa sin romper.
    """
    base = "users/u1/projects/1/input/"
    res1 = await lister.list_folder(base, recursive=True, limit=2)
    # Dos contratos posibles:
    if isinstance(res1, dict) and "items" in res1:
        assert len(res1["items"]) <= 2
        # Un segundo fetch con next_token, si viene
        if res1.get("next_token"):
            res2 = await lister.list_folder(base, recursive=True, limit=2, token=res1["next_token"])
            assert isinstance(res2, (list, dict))
    else:
        # Es lista simple: al menos no debe fallar
        assert isinstance(res1, list)
        assert len(res1) >= 2


@pytest.mark.asyncio
async def test_list_folder_rejects_insecure_paths(lister):
    """
    No debe permitir paths inseguros.
    """
    with pytest.raises(ValueError):
        await lister.list_folder("../escape", recursive=True)
    with pytest.raises(ValueError):
        await lister.list_folder("/absolute", recursive=False)


# Fin del archivo tests/modules/files/services/input_files/storage/test_file_list_storage.py
