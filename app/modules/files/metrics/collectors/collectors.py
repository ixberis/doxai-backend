
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/collectors/decorators.py

Decoradores opcionales para medir llamadas y latencias en memoria.

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations

import time
from functools import wraps
from typing import Callable, Any

from ..aggregators.metrics_storage import update_memory


def count_call(metric_key: str) -> Callable:
    def _wrap(fn: Callable) -> Callable:
        @wraps(fn)
        def _inner(*args: Any, **kwargs: Any):
            update_memory({metric_key: (update_memory.__dict__.get(metric_key, 0) + 1)})
            return fn(*args, **kwargs)
        return _inner
    return _wrap


def measure_latency(metric_key: str) -> Callable:
    def _wrap(fn: Callable) -> Callable:
        @wraps(fn)
        def _inner(*args: Any, **kwargs: Any):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                dt = time.perf_counter() - t0
                update_memory({metric_key: dt})
        return _inner
    return _wrap


# Fin del archivo backend/app/modules/files/metrics/collectors/decorators.py
