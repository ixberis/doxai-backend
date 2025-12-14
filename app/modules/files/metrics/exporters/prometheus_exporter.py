
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/exporters/prometheus_exporter.py

Traduce el snapshot DB de Files a formato Prometheus (texto plano).

Compatibilidad:
- Soporta tanto la forma v2 del snapshot (keys `total_files` / `total_bytes`,
  listas de dicts para status/by_type, listas de tuplas para series diarias)
  como formas anteriores donde se usaban `count` / `bytes` y dicts planos.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def _series_to_lines(metric: str, pairs: Iterable[Tuple[str, int]]) -> List[str]:
    """
    Convierte una serie [(fecha_iso, valor), ...] en líneas Prometheus.
    """
    lines: List[str] = []
    for ts, value in pairs:
        lines.append(f'{metric}{{day="{ts}"}} {int(value)}')
    return lines


def _get_overview_counts(overview: Dict[str, Any]) -> Tuple[int, int]:
    """
    Extrae (total_files, total_bytes) de un diccionario overview, soportando
    tanto claves v2 (`total_files`, `total_bytes`) como variantes legacy
    (`count`, `bytes`).
    """
    total_files = int(
        overview.get("total_files")
        or overview.get("count")
        or 0
    )
    total_bytes = int(
        overview.get("total_bytes")
        or overview.get("bytes")
        or 0
    )
    return total_files, total_bytes


def _normalize_status_entries(raw: Any) -> Dict[str, int]:
    """
    Normaliza la sección de status a un dict {status: count}, admitiendo:
    - dict plano: {"uploaded": 5, "processed": 3}
    - lista de dicts: [{"status": "uploaded", "count": 5}, ...]
    """
    out: Dict[str, int] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k)] = int(v or 0)
    elif isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status"))
            count = int(entry.get("count") or 0)
            out[status] = out.get(status, 0) + count
    return out


def _normalize_by_type_entries(raw: Any) -> Dict[str, int]:
    """
    Normaliza la sección de productos by_type a un dict {type: count}, admitiendo:
    - dict plano: {"report": 10, "dataset": 2}
    - lista de dicts: [{"type": "report", "count": 10}, ...]
    """
    out: Dict[str, int] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k)] = int(v or 0)
    elif isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            t = str(entry.get("type"))
            count = int(entry.get("count") or 0)
            out[t] = out.get(t, 0) + count
    return out


def snapshot_to_prometheus_text(snapshot: Dict[str, Any]) -> str:
    """
    Convierte el snapshot DB a texto Prometheus.

    Espera un snapshot con forma similar a:

        {
          "inputs": {
            "overview": {"total_files": ..., "total_bytes": ...},
            "status": [
                {"status": "uploaded", "count": 5},
                ...
            ],
            "daily_created": [("2025-01-01", 3), ...],
          },
          "products": {
            "overview": {...},
            "by_type": [...],
            "daily_generated": [...],
          },
          "activity": {
            "totals": {...},
            "downloads_daily": [...],
            "generated_daily": [...],
          },
        }

    pero también soporta variantes legacy donde overview usa claves
    `count` / `bytes` y status/by_type son dicts.
    """
    out: List[str] = []

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------
    inputs = snapshot.get("inputs", {}) or {}
    inputs_overview = inputs.get("overview", {}) or {}
    inputs_status_raw = inputs.get("status") or {}
    inputs_daily = inputs.get("daily_created") or []

    total_inputs, total_input_bytes = _get_overview_counts(inputs_overview)

    out.append("# HELP doxai_files_inputs_total Número de archivos insumo por proyecto")
    out.append("# TYPE doxai_files_inputs_total gauge")
    out.append(f"doxai_files_inputs_total {total_inputs}")

    out.append("# HELP doxai_files_inputs_bytes_total Tamaño total de insumos (bytes)")
    out.append("# TYPE doxai_files_inputs_bytes_total gauge")
    out.append(f"doxai_files_inputs_bytes_total {total_input_bytes}")

    # Status de inputs
    out.append("# HELP doxai_files_inputs_status Conteo por estado del pipeline de insumos")
    out.append("# TYPE doxai_files_inputs_status gauge")
    norm_status = _normalize_status_entries(inputs_status_raw)
    for status, ct in norm_status.items():
        out.append(f'doxai_files_inputs_status{{status="{status}"}} {ct}')

    # Serie diaria de creación de insumos
    out.append("# HELP doxai_files_inputs_daily_created Nuevos insumos por día")
    out.append("# TYPE doxai_files_inputs_daily_created gauge")
    # Se asume una lista de tuplas (fecha, valor); si no, se ignora silenciosamente
    if isinstance(inputs_daily, list):
        try:
            out.extend(_series_to_lines("doxai_files_inputs_daily_created", inputs_daily))  # type: ignore[arg-type]
        except Exception:
            # Si la forma no es la esperada, no rompemos el export
            pass

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------
    products = snapshot.get("products", {}) or {}
    products_overview = products.get("overview", {}) or {}
    products_by_type_raw = products.get("by_type") or {}
    products_daily = products.get("daily_generated") or []

    total_products, total_product_bytes = _get_overview_counts(products_overview)

    out.append("# HELP doxai_files_products_total Número de archivos producto por proyecto")
    out.append("# TYPE doxai_files_products_total gauge")
    out.append(f"doxai_files_products_total {total_products}")

    out.append("# HELP doxai_files_products_bytes_total Tamaño total de productos (bytes)")
    out.append("# TYPE doxai_files_products_bytes_total gauge")
    out.append(f"doxai_files_products_bytes_total {total_product_bytes}")

    out.append("# HELP doxai_files_products_by_type Conteo por tipo lógico de producto")
    out.append("# TYPE doxai_files_products_by_type gauge")
    norm_by_type = _normalize_by_type_entries(products_by_type_raw)
    for t, ct in norm_by_type.items():
        out.append(f'doxai_files_products_by_type{{type="{t}"}} {ct}')

    out.append("# HELP doxai_files_products_daily_generated Productos generados por día")
    out.append("# TYPE doxai_files_products_daily_generated gauge")
    if isinstance(products_daily, list):
        try:
            out.extend(_series_to_lines("doxai_files_products_daily_generated", products_daily))  # type: ignore[arg-type]
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Activity
    # ------------------------------------------------------------------
    activity = snapshot.get("activity", {}) or {}
    totals = activity.get("totals") or {}
    downloads_daily = activity.get("downloads_daily") or []
    generated_daily = activity.get("generated_daily") or []

    out.append("# HELP doxai_files_activity_totals Totales de eventos de actividad")
    out.append("# TYPE doxai_files_activity_totals counter")
    if isinstance(totals, dict):
        for ev, ct in totals.items():
            out.append(f'doxai_files_activity_totals{{event="{ev}"}} {int(ct or 0)}')

    out.append("# HELP doxai_files_activity_downloads_daily Descargas por día")
    out.append("# TYPE doxai_files_activity_downloads_daily gauge")
    if isinstance(downloads_daily, list):
        try:
            out.extend(
                _series_to_lines(
                    "doxai_files_activity_downloads_daily",
                    downloads_daily,  # type: ignore[arg-type]
                )
            )
        except Exception:
            pass

    out.append("# HELP doxai_files_activity_generated_daily Generaciones por día")
    out.append("# TYPE doxai_files_activity_generated_daily gauge")
    if isinstance(generated_daily, list):
        try:
            out.extend(
                _series_to_lines(
                    "doxai_files_activity_generated_daily",
                    generated_daily,  # type: ignore[arg-type]
                )
            )
        except Exception:
            pass

    return "\n".join(out) + "\n"


__all__ = ["snapshot_to_prometheus_text"]

# Fin del archivo backend/app/modules/files/metrics/exporters/prometheus_exporter.py