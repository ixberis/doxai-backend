
# -*- coding: utf-8 -*-
"""
backend/tests/modules/auth/metrics/test_auth_collectors.py

Pruebas unitarias para los collectors de métricas del módulo Auth.
Se valida que los contadores/gauges/histogramas acepten labels y puedan
incrementarse/observarse sin errores (sin PII, labels sanitizados).

Autor: Ixchel Beristain
Fecha: 08/11/2025
"""
import time

import pytest

from app.modules.auth.metrics.collectors.auth_collectors import (
    auth_registrations_total,
    auth_activations_total,
    auth_password_resets_total,
    auth_login_attempts_total,
    auth_login_latency_seconds,
    auth_active_sessions,
)


def _counter_child_value(counter, **labels) -> float:
    """Obtiene el valor actual de un Counter con labels (usando API interna)."""
    child = counter.labels(**labels)
    # prometheus_client usa un ValueClass con ._value.get()
    return float(child._value.get())  # type: ignore[attr-defined]


def _gauge_value(gauge) -> float:
    return float(gauge._value.get())  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "labels",
    [
        {"success": "true", "reason": "none"},
        {"success": "false", "reason": "invalid_credentials"},
        {"success": "false", "reason": "too_many_attempts"},
    ],
)
def test_auth_login_attempts_total_increments_per_label_set(labels):
    before = _counter_child_value(auth_login_attempts_total, **labels)
    auth_login_attempts_total.labels(**labels).inc()
    after = _counter_child_value(auth_login_attempts_total, **labels)
    assert after == pytest.approx(before + 1.0)


def test_auth_login_latency_seconds_observe_ok():
    start = time.perf_counter()
    # Simula una operación “rápida”
    time.sleep(0.001)
    elapsed = time.perf_counter() - start
    # No debe lanzar excepción
    auth_login_latency_seconds.observe(elapsed)


def test_auth_registrations_and_activations_counters_ok():
    before_r = float(auth_registrations_total._value.get())  # type: ignore[attr-defined]
    before_a = float(auth_activations_total._value.get())    # type: ignore[attr-defined]
    auth_registrations_total.inc()
    auth_activations_total.inc()
    after_r = float(auth_registrations_total._value.get())   # type: ignore[attr-defined]
    after_a = float(auth_activations_total._value.get())     # type: ignore[attr-defined]
    assert after_r == pytest.approx(before_r + 1.0)
    assert after_a == pytest.approx(before_a + 1.0)


@pytest.mark.parametrize("status", ["requested", "completed", "failed"])
def test_auth_password_resets_total_by_status_ok(status):
    before = _counter_child_value(auth_password_resets_total, status=status)
    auth_password_resets_total.labels(status=status).inc()
    after = _counter_child_value(auth_password_resets_total, status=status)
    assert after == pytest.approx(before + 1.0)


def test_auth_active_sessions_gauge_set_ok():
    before = _gauge_value(auth_active_sessions)
    auth_active_sessions.set(42)
    after = _gauge_value(auth_active_sessions)
    assert after == pytest.approx(42.0)
    # Restaurar a valor anterior (no obligatorio, pero amble)
    auth_active_sessions.set(before)

# Fin del archivo backend/tests/modules/auth/metrics/test_auth_collectors.py
