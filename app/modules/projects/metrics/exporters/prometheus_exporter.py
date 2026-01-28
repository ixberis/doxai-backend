
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/metrics/exporters/prometheus_exporter.py

Exportador de métricas del módulo Projects en formato Prometheus-text.
Equivalente al exporter del módulo Payments, adaptado a nombres y dominios
de Projects (projects_total, projects_by_state, etc.).

Ajuste 10/11/2025:
- Soporta métricas con y sin etiquetas en counters/gauges.
- Soporta histogramas completos: buckets, _count, _sum y +Inf.
- Sanitiza nombres/labels y escapa valores conforme a Prometheus text exposition.
- Compatibilidad hacia atrás con snapshots antiguos (dict plano de buckets).

Autor: Ixchel Beristain
Fecha de actualización: 10/11/2025
"""
from __future__ import annotations

from typing import Dict, List, Any, Iterable, Tuple, Optional

from app.modules.projects.metrics.collectors.metrics_collector import get_collector


# ---------------------------------------------------------------------------
# Saneamiento y helpers
# ---------------------------------------------------------------------------

def _sanitize_name(name: str) -> str:
    """
    Convierte un nombre interno a formato compatible con Prometheus.
    """
    return (
        name.replace(".", "_")
        .replace("-", "_")
        .replace(" ", "_")
        .lower()
    )


def _sanitize_label_name(name: str) -> str:
    return _sanitize_name(name)


def _escape_label_value(value: Any) -> str:
    """
    Escapa valores de etiquetas conforme a formato Prometheus:
    - backslash -> \\
    - double quote -> \"
    - newline -> \n
    """
    s = str(value)
    s = s.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    return s


def _format_labels(labels: Optional[Dict[str, Any]]) -> str:
    if not labels:
        return ""
    items = [f'{_sanitize_label_name(k)}="{_escape_label_value(v)}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(items) + "}"


def _iter_labeled_samples(value: Any) -> Iterable[Tuple[Optional[Dict[str, Any]], float]]:
    """
    Itera sobre muestras (labels, value) para counters/gauges con varias formas:
      - escalar: 42 -> [(None, 42)]
      - dict único: {"labels": {...}, "value": 10}
      - lista: [{"labels": {...}, "value": 10}, {"labels": {...}, "value": 5}]
    Ignora entradas inválidas sin romper la exportación.
    """
    # Escalar
    if isinstance(value, (int, float)):
        yield None, float(value)
        return

    # Dict único con labels/value
    if isinstance(value, dict) and "value" in value:
        labels = value.get("labels") if isinstance(value.get("labels"), dict) else None
        v = value["value"]
        if isinstance(v, (int, float)):
            yield labels, float(v)
        return

    # Lista de muestras
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict) or "value" not in item:
                continue
            labels = item.get("labels") if isinstance(item.get("labels"), dict) else None
            v = item["value"]
            if isinstance(v, (int, float)):
                yield labels, float(v)
        return

    # Fallback: ignora estructuras desconocidas


def _parse_labeled_name(name: str) -> tuple:
    """
    Parse metric name with embedded labels.
    
    Format: metric_name:label1=val1:label2=val2
    Returns: (metric_name, {label1: val1, label2: val2})
    
    Examples:
        "projects_lifecycle_requests_total:op=create:outcome=success"
        -> ("projects_lifecycle_requests_total", {"op": "create", "outcome": "success"})
    """
    if ":" not in name:
        return name, {}
    
    parts = name.split(":")
    metric_name = parts[0]
    labels = {}
    
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            labels[k] = v
    
    return metric_name, labels


def _normalize_histogram(value: Any) -> Iterable[Tuple[Optional[Dict[str, Any]], Dict[str, float], Optional[float], Optional[int]]]:
    """
    Normaliza histogramas a una secuencia de:
      (labels, buckets_dict, sum_opt, count_opt)

    Admite:
      - dict con {"buckets": {...}, "sum": x, "count": y, "labels": {...}}
      - lista de dicts anteriores (múltiples series etiquetadas)
      - dict plano de buckets {"0.1": 3, "0.5": 7, "1": 9}
    """
    # Caso: una sola serie como dict rico
    if isinstance(value, dict):
        if "buckets" in value:
            buckets = value.get("buckets") or {}
            labels = value.get("labels") if isinstance(value.get("labels"), dict) else None
            s = value.get("sum")
            c = value.get("count")
            s = float(s) if isinstance(s, (int, float)) else None
            c = int(c) if isinstance(c, int) else (int(c) if isinstance(c, float) else None)
            yield labels, {str(k): float(v) for k, v in buckets.items()}, s, c
            return
        else:
            # Dict plano de buckets (compatibilidad)
            yield None, {str(k): float(v) for k, v in value.items()}, None, None
            return

    # Caso: múltiples series etiquetadas
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            buckets = item.get("buckets") or {}
            if not isinstance(buckets, dict):
                continue
            labels = item.get("labels") if isinstance(item.get("labels"), dict) else None
            s = item.get("sum")
            c = item.get("count")
            s = float(s) if isinstance(s, (int, float)) else None
            c = int(c) if isinstance(c, int) else (int(c) if isinstance(c, float) else None)
            yield labels, {str(k): float(v) for k, v in buckets.items()}, s, c
        return

    # Fallback: nada


# ---------------------------------------------------------------------------
# Exportador
# ---------------------------------------------------------------------------

class PrometheusExporter:
    """
    Genera una representación en texto de todas las métricas internas del
    módulo Projects para que Prometheus las pueda leer.
    """

    def __init__(self) -> None:
        self.collector = get_collector()

    # ------------------------------------------------------------------
    # Export principal
    # ------------------------------------------------------------------
    def render(self) -> str:
        """
        Devuelve un string en formato Prometheus exposition (texto plano).
        """
        snapshot = self.collector.snapshot()
        lines: List[str] = []

        # ----------------
        # Counters
        # ----------------
        for name, value in snapshot.get("counters", {}).items():
            # Parse labels from name format: metric_name:label1=val1:label2=val2
            prom_name, parsed_labels = _parse_labeled_name(name)
            prom_name = _sanitize_name(prom_name)
            lines.append(f"# TYPE {prom_name} counter")
            for labels, val in _iter_labeled_samples(value):
                # Merge parsed labels with any from value structure
                merged_labels = {**parsed_labels, **(labels or {})}
                labels_str = _format_labels(merged_labels) if merged_labels else ""
                lines.append(f"{prom_name}{labels_str} {val}")

        # ----------------
        # Gauges
        # ----------------
        for name, value in snapshot.get("gauges", {}).items():
            prom_name, parsed_labels = _parse_labeled_name(name)
            prom_name = _sanitize_name(prom_name)
            lines.append(f"# TYPE {prom_name} gauge")
            for labels, val in _iter_labeled_samples(value):
                merged_labels = {**parsed_labels, **(labels or {})}
                labels_str = _format_labels(merged_labels) if merged_labels else ""
                lines.append(f"{prom_name}{labels_str} {val}")

        # ----------------
        # Histograms
        # ----------------
        for name, value in snapshot.get("histograms", {}).items():
            prom_name, parsed_labels = _parse_labeled_name(name)
            prom_name = _sanitize_name(prom_name)
            lines.append(f"# TYPE {prom_name} histogram")

            for labels, buckets, s_opt, c_opt in _normalize_histogram(value):
                # Merge parsed labels from name with histogram labels
                merged_labels = {**parsed_labels, **(labels or {})}
                
                # Ordenar por límite 'le' numérico cuando sea posible
                def _le_key(k: str) -> float:
                    try:
                        return float(k)
                    except Exception:
                        return float("inf") if k == "+Inf" else float("inf")

                sorted_items = sorted(buckets.items(), key=lambda kv: _le_key(kv[0]))

                # Conteo acumulado por bucket
                cumulative = 0.0
                total_seen = 0.0
                for le_str, count in sorted_items:
                    count = float(count)
                    total_seen += count
                    cumulative += count
                    labels_with_le = dict(merged_labels or {})
                    labels_with_le["le"] = le_str
                    lines.append(f'{prom_name}_bucket{_format_labels(labels_with_le)} {cumulative}')

                # Asegurar bucket +Inf
                labels_with_inf = dict(merged_labels or {})
                labels_with_inf["le"] = "+Inf"
                lines.append(f'{prom_name}_bucket{_format_labels(labels_with_inf)} {cumulative}')

                # _count y _sum
                total_count = int(c_opt) if c_opt is not None else int(total_seen)
                merged_labels_str = _format_labels(merged_labels) if merged_labels else ""
                lines.append(f"{prom_name}_count{merged_labels_str} {total_count}")
                if s_opt is not None:
                    lines.append(f"{prom_name}_sum{merged_labels_str} {float(s_opt)}")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Export simplificado (por si se usa en APIs)
    # ------------------------------------------------------------------
    def json_snapshot(self) -> Dict[str, Any]:
        """
        Devuelve el snapshot del collector en formato dict (útil para APIs REST).
        """
        return self.collector.snapshot()


# ---------------------------------------------------------------------------
# Helper global
# ---------------------------------------------------------------------------
def export_prometheus_text() -> str:
    """
    Genera el texto de métricas para Prometheus scrape.
    """
    exporter = PrometheusExporter()
    return exporter.render()


__all__ = ["PrometheusExporter", "export_prometheus_text"]

# Fin del archivo backend/app/modules/projects/metrics/exporters/prometheus_exporter.py