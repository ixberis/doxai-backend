# -*- coding: utf-8 -*-
import importlib
import logging
import sys
import pytest

json_logger = pytest.importorskip(
    "pythonjsonlogger", reason="Se omite test JSON si no está instalado python-json-logger"
)

def test_setup_logging_plain(monkeypatch):
    from app.shared.config.logging_config import setup_logging
    setup_logging(level="DEBUG", fmt="plain")
    logger = logging.getLogger("test_plain")
    # No debe fallar emitir logs
    logger.debug("hello plain")
    # Debe existir handler de consola
    assert any(isinstance(h, logging.StreamHandler) for h in logging.getLogger().handlers)

def test_setup_logging_json(monkeypatch):
    from app.shared.config.logging_config import setup_logging
    setup_logging(level="INFO", fmt="json")
    logger = logging.getLogger("test_json")
    logger.info("hello json")
    # Verifica que el formatter activo del root sea de jsonlogger
    found = False
    for h in logging.getLogger().handlers:
        fmt = getattr(h, "formatter", None)
        if fmt is not None and fmt.__class__.__module__.startswith("pythonjsonlogger"):
            found = True
            break
    assert found, "Se esperaba JsonFormatter activo en modo json"
# Fin del archivo backend/tests/shared/config/test_logging_config.py