# backend/tests/modules/files/services/analytics/conftest.py
# -*- coding: utf-8 -*-
"""
Fixtures compartidas para tests del módulo analytics.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone


@pytest.fixture
async def sample_user(db_session):
    """Crea un usuario de prueba usando el modelo real AppUser."""
    from app.modules.auth.models.user_models import AppUser
    from app.modules.auth.enums import UserRole, UserStatus
    
    # Email único por test para evitar UNIQUE constraint
    user_email = f"test.user.{uuid4().hex[:8]}@example.com"
    
    user = AppUser(
        user_full_name="Test User",
        user_email=user_email,
        user_password_hash="dummy_hash",
        user_role=UserRole.customer,
        user_status=UserStatus.active,
        user_is_activated=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def sample_project(db_session, sample_user):
    """Crea un proyecto de prueba."""
    from sqlalchemy import text
    
    # Limpiar datos previos para evitar violaciones de UNIQUE constraint
    await db_session.execute(text("DELETE FROM projects"))
    await db_session.commit()
    
    project_id = uuid4()
    
    # Columnas reales: created_at, updated_at (sin prefijo project_)
    await db_session.execute(
        text("""
            INSERT INTO projects 
            (id, user_id, user_email, project_name, project_slug, project_description, 
             project_state, project_status, created_at, updated_at)
            VALUES (:pid, :uid, :email, :name, :slug, :desc, :state, :status, :created, :updated)
        """),
        {
            "pid": str(project_id),
            "uid": str(sample_user.user_id),
            "email": sample_user.user_email,
            "name": "Test Project",
            "slug": "test-project",
            "desc": "A test project",
            "state": "created",
            "status": "in_process",
            "created": datetime.now(timezone.utc).isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
        }
    )
    await db_session.commit()
    
    class Project:
        pass
    project = Project()
    project.id = project_id
    project.project_id = project_id
    project.owner_id = sample_user.user_id
    return project
