
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/aggregators/metrics_storage.py

API de almacenamiento en memoria para contadores temporales (opcional).
Se deja como stub para paridad con Payments. Útil si se instrumentan
decorators en servicios para medir latencias in-memory.

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations

from typing import Any, Dict
import threading
import time


class _InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def set(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._data.update(payload)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_store = _InMemoryStore()


def snapshot_memory() -> Dict[str, Any]:
    """
    Devuelve el último snapshot in-memory (si se usa instrumentación opcional).
    """
    return {
        "ts": int(time.time()),
        "memory": _store.get(),
    }


def update_memory(payload: Dict[str, Any]) -> None:
    _store.set(payload)


def clear_memory() -> None:
    _store.clear()


# Fin del archivo backend/app/modules/files/metrics/aggregators/metrics_storage.py
