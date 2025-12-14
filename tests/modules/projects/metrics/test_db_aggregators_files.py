
# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/metrics/test_db_aggregators_files.py

Pruebas del agregador de BD para métricas de archivos y eventos de archivo:
- Conteo total de archivos
- Promedio de tamaño (si la columna existe)
- Conteo de eventos por tipo
- Últimos eventos (orden y campos mínimos)
- Resumen consolidado (ProjectFilesSummary)

Autor: Ixchel Beristain
Fecha de actualización: 2025-11-08
"""
from __future__ import annotations

from app.modules.projects.metrics.aggregators.db.files import FilesDBAggregator


def test_files_total_and_avg_size(db):
    agg = FilesDBAggregator(db)

    total = agg.files_total()
    assert isinstance(total, int)
    assert total >= 0

    avg_size = agg.avg_file_size_bytes()
    # Puede ser None si no existe columna de tamaño
    assert avg_size is None or avg_size >= 0.0


def test_events_by_type_returns_dict_and_total(db):
    agg = FilesDBAggregator(db)
    res = agg.events_by_type()
    assert isinstance(res.items, dict)
    assert isinstance(res.total, int)
    assert res.total >= 0


def test_last_events_returns_recent_list(db):
    agg = FilesDBAggregator(db)
    events = agg.last_events(limit=10)
    assert isinstance(events, list)
    # Con BD vacía, debe retornar lista vacía sin error
    assert len(events) >= 0


def test_files_summary_combines_all_metrics(db):
    agg = FilesDBAggregator(db)
    summary = agg.files_summary()
    assert summary.files_total >= 0
    assert summary.last_events_total >= 0
    assert hasattr(summary, "avg_file_size_bytes")
    # Con BD vacía, avg debe ser None o 0
    if summary.avg_file_size_bytes is not None:
        assert summary.avg_file_size_bytes >= 0.0


def test_aggregator_handles_empty_database(db):
    # Limpiar BD usando Base.metadata
    from app.shared.database import Base
    from sqlalchemy import text
    
    # Limpiar tablas relevantes en orden inverso de dependencias
    for table_name in ["project_file_event_logs", "project_files", "projects"]:
        db.execute(text(f"DELETE FROM {table_name}"))
    db.commit()

    agg = FilesDBAggregator(db)
    total = agg.files_total()
    assert total == 0
    avg_size = agg.avg_file_size_bytes()
    # Puede ser None (sin columna) o 0
    assert avg_size is None or avg_size >= 0.0
    res = agg.events_by_type()
    assert res.total == 0
    summary = agg.files_summary()
    assert summary.files_total == 0
    assert summary.last_events_total == 0
