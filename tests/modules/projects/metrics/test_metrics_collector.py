
# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/metrics/test_metrics_collector.py

Pruebas unitarias para el collector de métricas del módulo Projects.
Verifica:
- Incremento de contadores
- Asignación y suma en gauges
- Observación y acumulación en histogramas
- Snapshot global (serialización completa)
- Comportamiento aislado por instancia

Autor: Ixchel Beristain
Fecha de actualización: 2025-11-08
"""
import pytest
from app.modules.projects.metrics.collectors.metrics_collector import (
    ProjectsMetricsCollector,
    get_collector,
    Counter,
    Gauge,
    Histogram,
)


@pytest.fixture()
def collector_instance():
    """Crea una instancia aislada de collector para cada prueba."""
    return ProjectsMetricsCollector()


def test_counter_increment_and_snapshot(collector_instance):
    collector_instance.inc_counter("projects_total")
    collector_instance.inc_counter("projects_total", 4)
    snapshot = collector_instance.snapshot()
    assert snapshot["counters"]["projects_total"] == 5


def test_gauge_set_and_add(collector_instance):
    collector_instance.set_gauge("memory_usage", 10.0)
    collector_instance.add_gauge("memory_usage", 2.5)
    assert collector_instance.get_gauge("memory_usage") == pytest.approx(12.5, rel=1e-3)
    snapshot = collector_instance.snapshot()
    assert "memory_usage" in snapshot["gauges"]


def test_histogram_observation_and_buckets(collector_instance):
    # Observamos diferentes valores
    collector_instance.observe("ready_latency_seconds", 0.1)
    collector_instance.observe("ready_latency_seconds", 1.2)
    collector_instance.observe("ready_latency_seconds", 7.0)
    snapshot = collector_instance.snapshot()
    hist = snapshot["histograms"]["ready_latency_seconds"]
    # Debe contener buckets definidos (cadenas de límites)
    assert any(k for k in hist.keys() if k != "inf")
    # La suma de todos los buckets debe ser 3
    assert sum(hist.values()) == 3


def test_snapshot_structure_contains_all_sections(collector_instance):
    collector_instance.inc_counter("a")
    collector_instance.set_gauge("b", 1.0)
    collector_instance.observe("c", 0.2)
    snapshot = collector_instance.snapshot()
    assert set(snapshot.keys()) == {"counters", "gauges", "histograms"}
    assert "a" in snapshot["counters"]
    assert "b" in snapshot["gauges"]
    assert "c" in snapshot["histograms"]


def test_get_collector_returns_singleton():
    c1 = get_collector()
    c2 = get_collector()
    assert c1 is c2


def test_counter_thread_safety(monkeypatch):
    c = ProjectsMetricsCollector()

    # Simular acceso concurrente incrementando contador varias veces
    for _ in range(1000):
        c.inc_counter("concurrent_counter")

    assert c.get_counter("concurrent_counter") == 1000
    snapshot = c.snapshot()
    assert "concurrent_counter" in snapshot["counters"]
    assert snapshot["counters"]["concurrent_counter"] == 1000


def test_histogram_accumulates_to_inf_bucket():
    c = ProjectsMetricsCollector()
    # Observamos valores por encima del bucket máximo
    c.observe("duration_seconds", 999.0)
    hist = c.histogram_snapshot("duration_seconds")
    assert "inf" in hist
    assert hist["inf"] >= 1


def test_snapshot_isolation_between_instances():
    c1 = ProjectsMetricsCollector()
    c2 = ProjectsMetricsCollector()
    c1.inc_counter("alpha", 5)
    c2.inc_counter("beta", 2)
    snap1 = c1.snapshot()
    snap2 = c2.snapshot()
    assert "alpha" in snap1["counters"]
    assert "beta" not in snap1["counters"]
    assert "beta" in snap2["counters"]
    assert "alpha" not in snap2["counters"]

# Fin del archivo backend/tests/modules/projects/metrics/test_metrics_collector.py
