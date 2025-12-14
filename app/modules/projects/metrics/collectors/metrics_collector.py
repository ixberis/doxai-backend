
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/collectors/metrics_collector.py

Colector en memoria para métricas del módulo Projects.
Paridad conceptual con Payments:
- Contadores (counters) para eventos y totales.
- Medición de latencias (histogram-like buckets) para operaciones clave
  (p. ej., transición created→ready; operaciones de archivo).
- Instantáneo (snapshot) en memoria para exponer por rutas / snapshot_memory.

Ajuste 08/11/2025:
- Implementación thread-safe con Lock.
- API mínima para set/add/inc/observe y snapshot serializable.

Autor: Ixchel Beristain
Fecha de actualización: 08/11/2025
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Tuple, Optional


# ---------------------------------------------------------------------------
# Data classes para snapshots en memoria
# ---------------------------------------------------------------------------
@dataclass
class Counter:
    value: int = 0

    def inc(self, amount: int = 1) -> None:
        self.value += int(amount)


@dataclass
class Gauge:
    value: float = 0.0

    def set(self, value: float) -> None:
        self.value = float(value)

    def add(self, amount: float) -> None:
        self.value += float(amount)


@dataclass
class Histogram:
    """
    Histograma simple acumulativo con buckets definidos en segundos.
    `buckets` deben venir ordenados ascendentemente. Se cuenta en el primer
    bucket cuyo límite sea >= valor observado. El bucket '+Inf' se guarda con
    la llave `inf`.
    """
    buckets: List[float] = field(default_factory=lambda: [0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])
    counts: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.counts:
            # Inicializa en cero todos los buckets y el +Inf
            self.counts = {str(b): 0 for b in self.buckets}
            self.counts["inf"] = 0

    def observe(self, value: float) -> None:
        for b in self.buckets:
            if value <= b:
                self.counts[str(b)] += 1
                return
        self.counts["inf"] += 1

    def snapshot(self) -> Dict[str, int]:
        return dict(self.counts)


# ---------------------------------------------------------------------------
# Colector principal
# ---------------------------------------------------------------------------
class ProjectsMetricsCollector:
    """
    Colector en memoria para métricas de Projects.

    Nombres sugeridos (paridad con Payments):
    - counters:
        - projects_total
        - projects_by_state:<state>
        - projects_by_status:<status>
        - project_files_total
        - project_file_events_total:<event>
    - histograms:
        - projects_ready_time_seconds
    - gauges:
        - opcionales (ej. memoria usada por agregadores)
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}

    # ----------------------------- counters --------------------------------
    def inc_counter(self, name: str, amount: int = 1) -> None:
        with self._lock:
            c = self._counters.get(name)
            if c is None:
                c = Counter()
                self._counters[name] = c
            c.inc(amount)

    def get_counter(self, name: str) -> int:
        with self._lock:
            c = self._counters.get(name)
            return c.value if c else 0

    # ------------------------------ gauges ---------------------------------
    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            g = self._gauges.get(name)
            if g is None:
                g = Gauge()
                self._gauges[name] = g
            g.set(value)

    def add_gauge(self, name: str, amount: float) -> None:
        with self._lock:
            g = self._gauges.get(name)
            if g is None:
                g = Gauge()
                self._gauges[name] = g
            g.add(amount)

    def get_gauge(self, name: str) -> float:
        with self._lock:
            g = self._gauges.get(name)
            return g.value if g else 0.0

    # ---------------------------- histograms -------------------------------
    def _get_or_create_histogram(self, name: str, buckets: Optional[List[float]]) -> Histogram:
        h = self._histograms.get(name)
        if h is None:
            h = Histogram(buckets=buckets or Histogram().buckets)
            self._histograms[name] = h
        return h

    def observe(self, name: str, value_seconds: float, buckets: Optional[List[float]] = None) -> None:
        with self._lock:
            h = self._get_or_create_histogram(name, buckets)
            h.observe(value_seconds)

    def histogram_snapshot(self, name: str) -> Dict[str, int]:
        with self._lock:
            h = self._histograms.get(name)
            return h.snapshot() if h else {}

    # ----------------------------- snapshot --------------------------------
    def snapshot(self) -> dict:
        """
        Devuelve un dict serializable con todos los contadores, gauges e histogramas.
        Útil para exponer en /projects/metrics/snapshot/memory
        """
        with self._lock:
            return {
                "counters": {k: v.value for k, v in self._counters.items()},
                "gauges": {k: v.value for k, v in self._gauges.items()},
                "histograms": {k: v.snapshot() for k, v in self._histograms.items()},
            }


# ---------------------------------------------------------------------------
# Singleton opcional (facilita uso desde decoradores/rutas)
# ---------------------------------------------------------------------------
_collector_singleton: Optional[ProjectsMetricsCollector] = None


def get_collector() -> ProjectsMetricsCollector:
    global _collector_singleton
    if _collector_singleton is None:
        _collector_singleton = ProjectsMetricsCollector()
    return _collector_singleton


# ---------------------------------------------------------------------------
# Temporizador utilitario (context manager) para medir latencias ad-hoc
# ---------------------------------------------------------------------------
class Timer:
    """
    Temporizador simple para medición manual:
        with Timer(lambda dt: collector.observe("projects_ready_time_seconds", dt)):
            ... trabajo ...
    """
    def __init__(self, on_done):
        self.on_done = on_done
        self.t0 = 0.0

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.perf_counter() - self.t0
        try:
            self.on_done(float(dt))
        except Exception:
            # No romper el flujo por errores de métrica
            pass
        return False  # no suprimir excepciones


__all__ = [
    "ProjectsMetricsCollector",
    "get_collector",
    "Counter",
    "Gauge",
    "Histogram",
    "Timer",
]

# Fin del archivo backend\app\modules\projects\metrics\collectors\metrics_collector.py