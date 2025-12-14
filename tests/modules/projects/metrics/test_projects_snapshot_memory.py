
# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/metrics/test_snapshot_memory.py

Pruebas del endpoint /projects/metrics/snapshot/memory.
Valida:
- Código de estado 200
- Estructura {"success": true, "snapshot": {counters,gauges,histograms}}
- Refleja el estado del collector in-memory

Autor: Ixchel Beristain
Fecha de actualización: 2025-11-08
"""
from __future__ import annotations

from app.modules.projects.metrics.collectors.metrics_collector import get_collector


def test_snapshot_memory_returns_structure(client):
    resp = client.get("/projects/metrics/snapshot/memory")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "snapshot" in data
    snap = data["snapshot"]
    assert set(snap.keys()) == {"counters", "gauges", "histograms"}
    assert isinstance(snap["counters"], dict)
    assert isinstance(snap["gauges"], dict)
    assert isinstance(snap["histograms"], dict)


def test_snapshot_memory_reflects_collector_state(client):
    collector = get_collector()
    collector.inc_counter("alpha", 3)
    collector.set_gauge("beta", 2.0)
    collector.observe("gamma_seconds", 0.15)

    resp = client.get("/projects/metrics/snapshot/memory")
    data = resp.json()
    snap = data["snapshot"]

    assert snap["counters"].get("alpha") == 3
    assert snap["gauges"].get("beta") == 2.0
    # Para histograma, basta con que exista gamma_seconds y tenga conteos
    assert "gamma_seconds" in snap["histograms"]
    assert sum(snap["histograms"]["gamma_seconds"].values()) >= 1

# Fin del archivo backend/tests/modules/projects/metrics/test_snapshot_memory.py
