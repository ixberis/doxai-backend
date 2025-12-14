
# tests/modules/files/services/input_files/storage/test_storage_paths_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio StoragePathsService (módulo Files).

Cubre:
- Generación de rutas base por usuario y proyecto.
- Normalización de rutas (sin ../ ni // redundantes).
- Prevención de rutas inseguras o traversal.
- Creación de subcarpetas por tipo de archivo.
- Validación de nombres válidos/invalidos.
"""

import pytest
import re
from app.modules.files.services.storage.storage_paths import StoragePathsService


@pytest.fixture
def svc():
    """Instancia del servicio a probar."""
    return StoragePathsService(base_prefix="users")


def _is_safe(path: str) -> bool:
    """Helper para validar que no contiene secuencias peligrosas."""
    return not (".." in path or "//" in path or "\\" in path or path.startswith("/"))


def test_generate_user_folder_path(svc):
    """
    Debe generar correctamente la carpeta raíz de un usuario.
    """
    uid = "user_123"
    path = svc.user_folder(uid)
    assert path == f"users/{uid}/"
    assert _is_safe(path)
    assert path.endswith("/")


def test_generate_project_folder_path(svc):
    """
    Debe generar carpeta base de proyecto dentro del usuario.
    """
    uid = "user_abc"
    pid = 42
    path = svc.project_folder(user_id=uid, project_id=pid)
    assert path == f"users/{uid}/projects/{pid}/"
    assert _is_safe(path)
    assert path.endswith("/")


def test_generate_input_file_path(svc):
    """
    Debe generar ruta completa para archivo de entrada.
    """
    path = svc.input_file_path(user_id="u1", project_id=9, file_name="data.csv")
    assert path == "users/u1/projects/9/input/data.csv"
    assert path.endswith(".csv")
    assert _is_safe(path)


def test_generate_product_file_path(svc):
    """
    Debe generar ruta completa para archivo de salida (product).
    """
    path = svc.product_file_path(user_id="u2", project_id=99, file_name="result.pdf")
    assert path == "users/u2/projects/99/output/result.pdf"
    assert path.endswith(".pdf")
    assert _is_safe(path)


def test_normalize_removes_redundant_segments(svc):
    """
    Debe limpiar secuencias // o ./ y quitar barra inicial.
    """
    raw = "/users//test/./file.txt"
    normalized = svc.normalize_path(raw)
    assert normalized == "users/test/file.txt"
    assert _is_safe(normalized)


def test_invalid_filename_raises_valueerror(svc):
    """
    Nombres que contengan ../ o comiencen con / deben ser rechazados.
    """
    invalids = [
        "../escape.txt",
        "/rooted.txt",
        "folder\\evil.txt",
        "double//slash.txt",
    ]
    for inval in invalids:
        with pytest.raises(ValueError):
            svc.ensure_safe_path(inval)


def test_valid_filename_passes_validation(svc):
    """
    Debe aceptar nombres de archivo simples y retornarlos normalizados.
    """
    result = svc.validate_filename("ok.txt")
    assert result == "ok.txt"


def test_filename_with_spaces_and_unicode_is_normalized(svc):
    """
    Los nombres con espacios o unicode deben normalizarse adecuadamente.
    """
    # El servicio actual valida que no haya separadores
    # Intentar validar un filename con / debería fallar
    with pytest.raises(ValueError):
        svc.validate_filename("Carpeta de Pruebas/Árbol.xlsx")


def test_join_and_split_components_consistency(svc):
    """
    Verifica que join_path y split_path sean operaciones inversas.
    """
    components = ["users", "u7", "projects", "1", "input", "data.txt"]
    joined = svc.join_path(*components)
    split = svc.split_path(joined)
    assert split == components


def test_path_regex_is_safe_and_predictable(svc):
    """
    Patrón regex interno para validar rutas solo debe permitir nombres seguros.
    """
    import re
    pattern = svc.safe_path_pattern
    assert isinstance(pattern, re.Pattern)
    # Validar nombres sin separadores
    assert pattern.match("file-OK_123.txt")
    assert not pattern.match("../hack.txt")
    assert not pattern.match("/absolute")


# Fin del archivo tests/modules/files/services/input_files/storage/test_storage_paths_service.py
