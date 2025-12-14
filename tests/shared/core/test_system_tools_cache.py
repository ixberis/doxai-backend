# -*- coding: utf-8 -*-
import pytest

def test_check_ghostscript_availability(monkeypatch):
    import shutil
    from app.shared.core.system_tools_cache import check_ghostscript_availability

    # Simular que existe gswin64c
    monkeypatch.setattr(shutil, "which", lambda cmd: r"C:\Path\gswin64c.exe" if cmd == "gswin64c" else None)
    ok, path = check_ghostscript_availability()
    assert ok is True
    assert path.endswith("gswin64c.exe")

def test_check_poppler_availability(monkeypatch):
    import shutil
    from app.shared.core.system_tools_cache import check_poppler_availability

    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/pdftoppm" if cmd == "pdftoppm" else None)
    ok, path = check_poppler_availability()
    assert ok is True
    assert path.endswith("pdftoppm")

def test_check_tesseract_availability_found(monkeypatch):
    import shutil
    from app.shared.core.system_tools_cache import check_tesseract_availability

    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/tesseract")
    assert check_tesseract_availability() is True

def test_check_tesseract_availability_missing(monkeypatch):
    import shutil
    from app.shared.core.system_tools_cache import check_tesseract_availability

    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    assert check_tesseract_availability() is False
# Fin del archivo