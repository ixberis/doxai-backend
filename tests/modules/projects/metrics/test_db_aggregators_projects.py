
# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/metrics/test_db_aggregators_projects.py

Pruebas directas del agregador de BD para métricas de Proyectos:
- Total de proyectos
- Distribución por estado y status
- Series por ventana temporal (ready por día)
- Lead time created→ready (promedio opcional)

Autor: Ixchel Beristain
Fecha de actualización: 2025-11-08
"""
from __future__ import annotations

import datetime as dt

from app.modules.projects.metrics.aggregators.db.projects import ProjectsDBAggregator
from app.modules.projects.models.project_models import Project
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus


def test_projects_totals_and_distributions(db):
    agg = ProjectsDBAggregator(db)

    total = agg.projects_total()
    assert total >= 0

    by_state = agg.projects_by_state()
    assert by_state.total == total
    assert isinstance(by_state.items, dict)

    by_status = agg.projects_by_status()
    assert by_status.total == total
    assert isinstance(by_status.items, dict)


def test_projects_ready_by_window_returns_buckets(db):
    agg = ProjectsDBAggregator(db)
    buckets = agg.projects_ready_by_window(date_trunc="day", limit_buckets=30)
    assert isinstance(buckets, list)
    assert all(hasattr(b, "bucket_start") and hasattr(b, "value") for b in buckets)
    total_ready = sum(b.value for b in buckets) if buckets else 0.0
    assert total_ready >= 0.0


def test_ready_lead_time_is_optional_but_stable(db):
    """
    Dependiendo del dialecto SQL, AVG(epoch) puede o no estar soportado.
    Por eso validamos que:
      - la estructura exista
      - avg_seconds sea float o None (no debe lanzar)
    """
    agg = ProjectsDBAggregator(db)
    lt = agg.ready_lead_time()
    assert hasattr(lt, "avg_seconds")
    # Puede ser None en SQLite fallback; si no es None, debe ser >= 0
    if lt.avg_seconds is not None:
        assert lt.avg_seconds >= 0.0


def test_projects_distributions_with_empty_db(db):
    """
    Cuando no hay datos, los totales deben ser 0 y estructuras vacías válidas.
    """
    # Vaciar todo lo que haya en la BD usando Base.metadata
    from sqlalchemy import text
    
    # Limpiar tablas relevantes en orden inverso de dependencias
    for table_name in ["project_file_event_logs", "project_files", "projects"]:
        db.execute(text(f"DELETE FROM {table_name}"))
    db.commit()

    agg = ProjectsDBAggregator(db)
    assert agg.projects_total() == 0

    by_state = agg.projects_by_state()
    assert by_state.total == 0
    assert by_state.items == {}

    by_status = agg.projects_by_status()
    assert by_status.total == 0
    assert by_status.items == {}

    buckets = agg.projects_ready_by_window()
    assert isinstance(buckets, list)
    assert len(buckets) == 0

    lt = agg.ready_lead_time()
    assert hasattr(lt, "avg_seconds")  # puede ser None en vacío
