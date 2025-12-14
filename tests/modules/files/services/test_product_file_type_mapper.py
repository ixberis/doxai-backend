
# tests/modules/files/services/test_product_file_type_mapper.py
# -*- coding: utf-8 -*-
"""
Tests para el servicio utilitario product_file_type_mapper.py

Objetivo:
Mapear un archivo (por extensión y/o MIME) a un ProductFileType canónico.

Cubre:
- Mapeo por extensión común (pdf, docx, xlsx, pptx, csv, json, png, jpg, md, txt, zip).
- Mapeo por MIME type (application/pdf, image/png, text/markdown, etc.).
- Preferencia de MIME sobre extensión cuando hay conflicto.
- Normalización case-insensitive.
- Fallback a ProductFileType.other cuando no hay coincidencia.
- Tolerancia a inputs incompletos (None o strings vacíos).
"""

import pytest

from app.modules.files.enums.product_file_type_enum import ProductFileType
from app.modules.files.services.product_file_type_mapper import (
    guess_product_file_type,        # (file_name: str | None = None, mime_type: str | None = None) -> ProductFileType
    guess_from_extension,           # (file_name: str) -> ProductFileType
    guess_from_mime,                # (mime_type: str) -> ProductFileType
)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("reporte.pdf", ProductFileType.report),
        ("Reporte.PDF", ProductFileType.report),
        ("documento.docx", ProductFileType.document),
        ("presentacion.pptx", ProductFileType.presentation),
        ("datos.xlsx", ProductFileType.spreadsheet),
        ("tabla.csv", ProductFileType.dataset),
        ("dataset.json", ProductFileType.dataset),
        ("grafica.png", ProductFileType.chart),
        ("foto.JPG", ProductFileType.image),
        ("readme.md", ProductFileType.document),
        ("nota.txt", ProductFileType.document),
        ("archivo.zip", ProductFileType.archive),
    ],
)
def test_guess_from_extension_basic(name, expected):
    assert guess_from_extension(name) == expected


@pytest.mark.parametrize(
    "mime,expected",
    [
        ("application/pdf", ProductFileType.report),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ProductFileType.document),
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ProductFileType.presentation),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ProductFileType.spreadsheet),
        ("text/csv", ProductFileType.dataset),
        ("application/json", ProductFileType.dataset),
        ("image/png", ProductFileType.image),   # algunas implementaciones lo devuelven como chart si tiene 'chart' en nombre; aquí base: image
        ("image/jpeg", ProductFileType.image),
        ("text/markdown", ProductFileType.document),
        ("text/plain", ProductFileType.document),
        ("application/zip", ProductFileType.archive),
    ],
)
def test_guess_from_mime_basic(mime, expected):
    assert guess_from_mime(mime) == expected


def test_guess_prefers_mime_over_extension_on_conflict(monkeypatch):
    """
    Si el MIME apunta a 'dataset' pero la extensión sugiere 'document',
    debe prevalecer el MIME (p. ej., un .txt con content-type application/json).
    """
    name = "datos.txt"
    mime = "application/json"

    # Aseguramos que la ext .txt normalmente mapea a document:
    assert guess_from_extension(name) == ProductFileType.document
    # Al combinar con MIME json => dataset
    assert guess_product_file_type(file_name=name, mime_type=mime) == ProductFileType.dataset


@pytest.mark.parametrize(
    "name,mime,expected",
    [
        ("grafica.png", None, ProductFileType.chart),  # si tu mapper considera 'grafica'/'chart' en nombre => chart
        ("graph.PNG", None, ProductFileType.chart),
        ("imagen.png", "image/png", ProductFileType.image),  # MIME explícito debe prevalecer
        ("resultado.pdf", "application/pdf", ProductFileType.report),
        ("reporte.final.PDF", "application/octet-stream", ProductFileType.report),  # ext prevalece si MIME es genérico
    ],
)
def test_guess_combined_heuristics(name, mime, expected):
    got = guess_product_file_type(file_name=name, mime_type=mime)
    assert got == expected


@pytest.mark.parametrize(
    "name,mime",
    [
        (None, None),
        ("", ""),
        ("archivo.desconocido", None),
        ("sin_tipo.bin", "application/octet-stream"),
    ],
)
def test_fallback_other_on_unknown(name, mime):
    assert guess_product_file_type(file_name=name, mime_type=mime) == ProductFileType.other


def test_case_insensitive_inputs():
    """
    Debe ser insensible a mayúsculas/minúsculas en extensión y MIME.
    """
    assert guess_product_file_type(file_name="DOC.PdF") == ProductFileType.report
    assert guess_product_file_type(mime_type="IMAGE/JPEG") == ProductFileType.image
    assert guess_from_extension("DATA.CSV") == ProductFileType.dataset
    assert guess_from_mime("APPLICATION/ZIP") == ProductFileType.archive


# Fin del archivo tests/modules/files/services/test_product_file_type_mapper.py
