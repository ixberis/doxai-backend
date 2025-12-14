
# -*- coding: utf-8 -*-
"""
backend/tests/modules/projects/metrics/conftest.py

Fixtures para pruebas de métricas del módulo Projects:
- Cliente de pruebas montando el router principal (incluye /projects/metrics/*)
- Sesión de BD SQLite en memoria + creación de tablas ORM
- Semilla mínima de datos (proyectos/listos, archivos, eventos) para snapshot DB
- Limpieza del collector in-memory entre tests

Autor: Ixchel Beristain
Fecha de actualización: 2025-11-08
"""
from __future__ import annotations

import datetime as dt
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Router principal de Projects (ya incluye métricas)
from app.modules.projects.routes import get_projects_router

# Dependencias a sobreescribir en los tests
from app.shared.database.database import get_db
from app.modules.auth.services import get_current_user

# ORM base y modelos del módulo Projects
from app.shared.database.base import Base  # Base declarativa global
from app.modules.projects.models.project_models import Project
from app.modules.projects.models.project_file_models import ProjectFile
from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog
from app.modules.projects.enums.project_state_enum import ProjectState
from app.modules.projects.enums.project_status_enum import ProjectStatus
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent

# Collector (para restaurar entre pruebas)
from app.modules.projects.metrics.collectors.metrics_collector import get_collector


# ---------------------------------------------------------------------------
# SQLite en memoria para pruebas
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite://", echo=False, future=True)
    # Crear todas las tablas conocidas por los modelos registrados en Base
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)
    session = SessionLocal()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Overrides de dependencias + TestClient
# ---------------------------------------------------------------------------
@pytest.fixture()
def app_client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Monta un FastAPI mínimo e incluye el router principal de Projects.
    Sobrescribe get_db y get_current_user.
    """
    app = FastAPI()

    # Dependencia de DB → usar la sesión de prueba
    def _get_db_override() -> Generator[Session, None, None]:
        yield db_session

    # Dependencia de auth → usuario fake estable
    def _get_user_override():
        return {"id": "11111111-1111-1111-1111-111111111111", "email": "user@test.local"}

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = _get_user_override

    # Incluye el ensamblador de Projects (ya incluye /projects/metrics/*)
    app.include_router(get_projects_router())

    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Limpieza del collector en memoria entre pruebas
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def collector_clean():
    """
    Limpia el collector singleton para cada prueba.
    """
    c = get_collector()
    # Reset interno sin reemplazar la instancia
    c._counters.clear()
    c._gauges.clear()
    c._histograms.clear()
    yield
    c._counters.clear()
    c._gauges.clear()
    c._histograms.clear()


# ---------------------------------------------------------------------------
# Semilla mínima de datos para snapshot DB
# ---------------------------------------------------------------------------
@pytest.fixture()
def seed_projects_data(db_session: Session):
    """
    Inserta:
    - Proyecto A (READY) con ready_at → para series por ventana y lead-time
    - Proyecto B (DRAFT)
    - 1 archivo para A (con tamaño si existe la columna)
    - 2 eventos de archivo para A
    """
    now = dt.datetime.utcnow()
    created_at_a = now - dt.timedelta(hours=2)
    ready_at_a = now - dt.timedelta(minutes=30)

    # Proyecto A: READY
    proj_a = Project(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        user_id="11111111-1111-1111-1111-111111111111",
        project_name="Proyecto A",
        project_slug="proyecto-a",
        state=ProjectState.ready,
        status=ProjectStatus.active,
        created_at=created_at_a,
        ready_at=ready_at_a,
    )

    # Proyecto B: DRAFT
    proj_b = Project(
        id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        user_id="11111111-1111-1111-1111-111111111111",
        project_name="Proyecto B",
        project_slug="proyecto-b",
        state=ProjectState.draft,
        status=ProjectStatus.active,
        created_at=now - dt.timedelta(hours=1),
    )

    db_session.add_all([proj_a, proj_b])
    db_session.flush()

    # Archivo del proyecto A (si existe columna size_bytes/file_size/size, usar size_bytes si está)
    file_kwargs = dict(
        id="f0000000-0000-0000-0000-000000000001",
        project_id=proj_a.id,
        path="inbox/doc1.pdf",
        created_at=now - dt.timedelta(minutes=40),
    )
    for size_name in ("size_bytes", "file_size", "size"):
        if hasattr(ProjectFile, size_name):
            file_kwargs[size_name] = 2048
            break

    pf = ProjectFile(**file_kwargs)
    db_session.add(pf)
    db_session.flush()

    # Eventos del archivo
    ev1 = ProjectFileEventLog(
        id="e0000000-0000-0000-0000-000000000001",
        project_id=proj_a.id,
        file_id=pf.id,
        event_type=ProjectFileEvent.uploaded,
        created_at=now - dt.timedelta(minutes=39),
    )
    ev2 = ProjectFileEventLog(
        id="e0000000-0000-0000-0000-000000000002",
        project_id=proj_a.id,
        file_id=pf.id,
        event_type=ProjectFileEvent.validated,
        created_at=now - dt.timedelta(minutes=35),
    )
    db_session.add_all([ev1, ev2])
    db_session.commit()

    return {"proj_a": proj_a, "proj_b": proj_b, "file": pf, "events": [ev1, ev2]}

# Fin del archivo backend/tests/modules/projects/metrics/conftest.py
