
# tests/modules/files/services/downloads/test_zip_creator_service.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio ZipCreatorService del módulo Files.

Cubre:
- Creación de un archivo ZIP válido a partir de múltiples blobs.
- Preservación de nombres de archivo y jerarquía.
- Manejo de streams y archivos grandes (chunked writing).
- Excepción controlada si un archivo falla durante la escritura.
- Tamaño y estructura del ZIP coherentes.
"""

import io
import os
import zipfile
import pytest

from app.modules.files.services.zip_creator_service import ZipCreatorService


@pytest.fixture
def svc(tmp_path):
    """Instancia del servicio a probar."""
    return ZipCreatorService(tmp_dir=tmp_path)


def test_create_zip_from_multiple_files(tmp_path, svc):
    """
    Debe crear un ZIP con múltiples archivos y rutas jerárquicas.
    """
    files = {
        "input/data1.txt": b"Contenido 1",
        "input/data2.txt": b"Contenido 2",
        "output/result.pdf": b"%PDF-1.7 simulated",
    }

    zip_bytes = svc.create_zip(files)

    assert isinstance(zip_bytes, (bytes, bytearray))
    assert len(zip_bytes) > 100

    # Validar ZIP
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert "input/data1.txt" in names
        assert "input/data2.txt" in names
        assert "output/result.pdf" in names

        # Contenido coherente
        assert zf.read("input/data1.txt").startswith(b"Contenido 1")
        assert zf.read("output/result.pdf").startswith(b"%PDF-1.7")


def test_create_zip_handles_empty_files(tmp_path, svc):
    """
    Debe aceptar archivos vacíos sin errores.
    """
    files = {"empty.txt": b""}
    zip_bytes = svc.create_zip(files)

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert "empty.txt" in names
        assert zf.read("empty.txt") == b""


def test_create_zip_rejects_invalid_input_type(tmp_path, svc):
    """
    Debe lanzar ValueError si el input no es dict[str, bytes].
    """
    invalid_data = ["a.txt", b"data"]
    with pytest.raises(ValueError):
        svc.create_zip(invalid_data)


def test_create_zip_continues_after_one_file_failure(tmp_path):
    """
    Debe continuar con los demás archivos si uno falla en escritura.
    """
    from app.modules.files.services.zip_creator_service import BrokenZipCreator

    svc = BrokenZipCreator(tmp_dir=tmp_path)
    files = {
        "ok1.txt": b"OK",
        "fail.txt": b"FAIL",
        "ok2.txt": b"OK2",
    }

    zip_bytes = svc.create_zip(files)

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert "ok1.txt" in names
        assert "ok2.txt" in names
        assert "fail.txt" not in names  # el fallido se omite


def test_create_zip_large_files_chunked(tmp_path, svc):
    """
    Debe escribir archivos grandes en chunks sin corromper el ZIP.
    """
    large_file = os.urandom(1024 * 256)  # 256 KB
    files = {"large.bin": large_file}

    zip_bytes = svc.create_zip(files, chunk_size=32 * 1024)
    assert len(zip_bytes) > 10000

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        extracted = zf.read("large.bin")
        assert extracted == large_file


# Fin del archivo tests/modules/files/services/downloads/test_zip_creator_service.py