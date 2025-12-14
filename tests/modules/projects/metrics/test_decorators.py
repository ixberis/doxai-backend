
# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/metrics/test_decorators.py

Pruebas de los decoradores de instrumentación del módulo Projects:
- @count_calls
- @measure_time_seconds
- @observe_exceptions
- @instrument

Autor: Ixchel Beristain
Fecha de actualización: 2025-11-08
"""
from __future__ import annotations

import pytest

from app.modules.projects.metrics.collectors.metrics_collector import get_collector
from app.modules.projects.metrics.collectors.decorators import (
    count_calls,
    measure_time_seconds,
    observe_exceptions,
    instrument,
)


def test_count_calls_increments_on_success():
    collector = get_collector()

    @count_calls("test_calls_total")
    def ok():
        return "done"

    # Dos llamadas exitosas
    assert ok() == "done"
    assert ok() == "done"

    snap = collector.snapshot()
    assert snap["counters"].get("test_calls_total", 0) == 2


def test_count_calls_does_not_increment_on_error():
    collector = get_collector()

    @count_calls("test_calls_total_err")
    def fails():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        fails()

    snap = collector.snapshot()
    # No debe incrementar en caso de excepción
    assert snap["counters"].get("test_calls_total_err", 0) == 0


def test_measure_time_seconds_records_histogram():
    collector = get_collector()

    @measure_time_seconds("fn_duration_seconds")
    def quick():
        # trabajo trivial
        return 42

    assert quick() == 42
    # Debe existir un histograma con al menos 1 conteo
    hist = collector.snapshot()["histograms"].get("fn_duration_seconds", {})
    assert sum(hist.values()) >= 1


def test_observe_exceptions_increments_on_failure():
    collector = get_collector()

    @observe_exceptions("fn_errors_total")
    def sometimes_fail(flag: bool):
        if flag:
            raise ValueError("bad")
        return "ok"

    assert sometimes_fail(False) == "ok"
    with pytest.raises(ValueError):
        sometimes_fail(True)

    snap = collector.snapshot()
    # Debe contar 1 error
    assert snap["counters"].get("fn_errors_total", 0) == 1


def test_instrument_combines_counter_and_histogram():
    collector = get_collector()

    @instrument("pipeline_step")
    def step(x: int) -> int:
        return x * 2

    assert step(5) == 10
    assert step(1) == 2

    snap = collector.snapshot()
    # Contador de llamadas
    assert snap["counters"].get("pipeline_step_calls_total", 0) == 2
    # Histograma de duración
    hist = snap["histograms"].get("pipeline_step_duration_seconds", {})
    assert sum(hist.values()) >= 2

# Fin del archivo backend/tests/modules/projects/metrics/test_decorators.py
