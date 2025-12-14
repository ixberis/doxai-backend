# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/tests/conftest.py

Fixtures compartidas para tests del módulo de proyectos.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.modules.projects.enums import ProjectState
from app.modules.auth.models import User
from app.modules.projects.models import Project, ProjectActivity
from app.shared.utils.security import hash_password


@pytest.fixture
def sample_user(db_session: Session):
    """Crea un usuario de prueba"""
    user = User(
        user_email="project.owner@example.com",
        password_hash=hash_password("TestPass123!"),
        user_full_name="Project Owner",
        user_is_activated=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def sample_project(db_session: Session, sample_user):
    """Crea un proyecto de prueba"""
    project = Project(
        user_id=sample_user.user_id,
        user_email=sample_user.user_email,
        project_name="Test Project",
        project_slug="test-project",
        project_description="A test project for unit testing",
        state=ProjectState.CREATED,
        project_is_archived=False,
        project_is_closed=False,
        project_tags=["test", "sample"],
        project_created_at=datetime.now(timezone.utc),
        project_updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def closed_project(db_session: Session, sample_user):
    """Crea un proyecto cerrado"""
    project = Project(
        user_id=sample_user.user_id,
        user_email=sample_user.user_email,
        project_name="Closed Project",
        project_slug="closed-project",
        project_description="A closed project",
        state=ProjectState.READY,
        project_is_archived=False,
        project_is_closed=True,
        project_closed_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def archived_project(db_session: Session, sample_user):
    """Crea un proyecto archivado"""
    project = Project(
        user_id=sample_user.user_id,
        user_email=sample_user.user_email,
        project_name="Archived Project",
        project_slug="archived-project",
        project_description="An archived project",
        state=ProjectState.READY,
        project_is_archived=True,
        project_is_closed=False,
        project_archived_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def sample_activity(db_session: Session, sample_project, sample_user):
    """Crea una actividad de prueba"""
    activity = ProjectActivity(
        project_id=sample_project.project_id,
        user_id=sample_user.user_id,
        user_email=sample_user.user_email,
        project_action_type="CREATED",
        project_action_details="Proyecto creado",
        project_action_metadata={"initial_phase": "CREATED"},
        project_action_created_at=datetime.now(timezone.utc),
    )
    db_session.add(activity)
    db_session.commit()
    db_session.refresh(activity)
    return activity
