
# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/metrics/test_snapshot_db.py

Pruebas del endpoint /projects/metrics/snapshot/db.
Valida:
- Código de estado 200
- Estructura completa SnapshotDBResponse
- Valores coherentes con los datos sembrados (fixtures)
- Manejo correcto cuando no hay datos (estructura vacía pero válida)

Autor: Ixchel Beristain
Fecha de actualización: 2025-11-08
"""
from __future__ import annotations

from app.modules.projects.metrics.schemas.metrics_schemas import ProjectMetricsSnapshotDB


def test_snapshot_db_returns_structure(client):
    """
    Verifica que el snapshot DB devuelva los campos esperados.
    """
    resp = client.get("/projects/metrics/snapshot/db")
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    snapshot = data["snapshot"]
    # Validar estructura base
    expected_keys = {
        "projects_total",
        "projects_by_state",
        "projects_by_status",
        "projects_ready_by_window",
        "ready_lead_time",
        "files_summary",
        "file_events_by_type",
    }
    assert set(snapshot.keys()) == expected_keys

    # Validar tipos básicos
    assert isinstance(snapshot["projects_total"], int)
    assert isinstance(snapshot["projects_by_state"], dict)
    assert isinstance(snapshot["projects_by_status"], dict)
    assert isinstance(snapshot["projects_ready_by_window"], list)
    assert isinstance(snapshot["ready_lead_time"], dict)
    assert isinstance(snapshot["files_summary"], dict)
    assert isinstance(snapshot["file_events_by_type"], dict)

    # Validar coherencia (sin asumir datos específicos)
    assert snapshot["projects_total"] >= 0
    assert "items" in snapshot["projects_by_state"]
    assert "items" in snapshot["projects_by_status"]
    assert snapshot["files_summary"]["files_total"] >= 0
    assert snapshot["file_events_by_type"]["total"] >= 0


def test_snapshot_db_empty_database_returns_valid_structure(client, db):
    """
    Si la base está vacía, el snapshot debe devolver ceros y estructuras vacías sin error.
    """
    # Limpieza total usando text() para compatibilidad SQLAlchemy 2.x
    from sqlalchemy import text
    
    # Limpiar tablas relevantes en orden inverso de dependencias
    for table_name in ["project_file_event_logs", "project_files", "projects"]:
        db.execute(text(f"DELETE FROM {table_name}"))
    db.commit()

    resp = client.get("/projects/metrics/snapshot/db")
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    snapshot = ProjectMetricsSnapshotDB(**data["snapshot"])
    # Totales en cero y estructuras vacías
    assert snapshot.projects_total == 0
    assert snapshot.projects_by_state.total == 0
    assert snapshot.projects_by_status.total == 0
    assert snapshot.files_summary.files_total == 0
    assert snapshot.file_events_by_type.total == 0

# Fin del archivo backend/tests/modules/projects/metrics/test_snapshot_db.py
