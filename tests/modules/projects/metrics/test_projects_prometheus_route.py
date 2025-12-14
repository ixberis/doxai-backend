
# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/metrics/test_prometheus_route.py

Pruebas del endpoint /projects/metrics/prometheus.
Valida:
- Código de estado 200
- Content-Type correcto (text/plain)
- Presencia de líneas # TYPE ... counter/gauge/histogram
- Formato compatible con Prometheus exposition text

Autor: Ixchel Beristain
Fecha de actualización: 2025-11-08
"""
import re
from app.modules.projects.metrics.collectors.metrics_collector import get_collector


def test_prometheus_route_returns_valid_text(client):
    """
    Verifica que el endpoint devuelva texto válido con métricas en formato Prometheus.
    """
    collector = get_collector()
    # Sembrar algunas métricas
    collector.inc_counter("projects_total", 3)
    collector.set_gauge("memory_usage_bytes", 128.0)
    collector.observe("projects_ready_time_seconds", 1.5)

    resp = client.get("/projects/metrics/prometheus")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text.strip()
    # Debe contener TYPE lines y métricas con valores numéricos
    assert re.search(r"^# TYPE projects_total counter", text, re.MULTILINE)
    assert re.search(r"^projects_total\s+\d+", text, re.MULTILINE)
    assert re.search(r"projects_ready_time_seconds_bucket", text)
    assert re.search(r"projects_ready_time_seconds_count", text)
    assert "memory_usage_bytes" in text


def test_prometheus_output_includes_all_metric_types(client):
    """
    Comprueba que los tres tipos (counter, gauge, histogram) estén presentes.
    """
    collector = get_collector()
    collector.inc_counter("jobs_processed_total", 1)
    collector.set_gauge("active_jobs", 5)
    collector.observe("job_duration_seconds", 0.25)

    resp = client.get("/projects/metrics/prometheus")
    text = resp.text
    assert "# TYPE jobs_processed_total counter" in text
    assert "# TYPE active_jobs gauge" in text
    assert "# TYPE job_duration_seconds histogram" in text

# Fin del archivo backend/tests/modules/projects/metrics/test_prometheus_route.py
