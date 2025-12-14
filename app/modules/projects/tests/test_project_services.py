# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/tests/test_services.py

Tests para los servicios del módulo de proyectos.

Autor: DoxAI
Fecha: 2025-10-18
"""

import pytest
from uuid import uuid4
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.modules.projects.services import ProjectService, ProjectActivityService
from app.modules.projects.schemas import ProjectCreate, ProjectActivityCreate
from app.modules.projects.enums import ProjectState


class TestProjectService:
    """Tests para ProjectService"""

    def test_create_project(self, db_session: Session, sample_user):
        """Test: crear proyecto básico"""
        service = ProjectService(db_session)
        
        project_data = ProjectCreate(
            project_name="New Test Project",
            project_description="Test description"
        )
        
        project = service.create_project(
            user_id=sample_user.user_id,
            user_email=sample_user.user_email,
            data=project_data
        )
        
        assert project.project_name == "New Test Project"
        assert project.project_slug == "new-test-project"
        assert project.state == ProjectState.CREATED
        assert project.project_is_archived is False
        assert project.project_is_closed is False

    def test_create_project_duplicate_name(self, db_session: Session, sample_user, sample_project):
        """Test: crear proyecto con nombre duplicado"""
        service = ProjectService(db_session)
        
        project_data = ProjectCreate(
            project_name=sample_project.project_name,  # Nombre duplicado
            project_description="Duplicate"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            service.create_project(
                user_id=sample_user.user_id,
                user_email=sample_user.user_email,
                data=project_data
            )
        
        assert exc_info.value.status_code == 409

    def test_get_project_by_id(self, db_session: Session, sample_project, sample_user):
        """Test: obtener proyecto por ID"""
        service = ProjectService(db_session)
        
        project = service.get_project_by_id(
            project_id=sample_project.project_id,
            user_id=sample_user.user_id
        )
        
        assert project.project_id == sample_project.project_id
        assert project.project_name == sample_project.project_name

    def test_get_project_not_found(self, db_session: Session, sample_user):
        """Test: proyecto no encontrado"""
        service = ProjectService(db_session)
        
        with pytest.raises(HTTPException) as exc_info:
            service.get_project_by_id(
                project_id=uuid4(),
                user_id=sample_user.user_id
            )
        
        assert exc_info.value.status_code == 404

    def test_get_project_forbidden(self, db_session: Session, sample_project):
        """Test: acceso denegado a proyecto de otro usuario"""
        service = ProjectService(db_session)
        other_user_id = uuid4()
        
        with pytest.raises(HTTPException) as exc_info:
            service.get_project_by_id(
                project_id=sample_project.project_id,
                user_id=other_user_id
            )
        
        assert exc_info.value.status_code == 403

    def test_get_projects_by_user(self, db_session: Session, sample_user, sample_project, closed_project):
        """Test: obtener todos los proyectos del usuario"""
        service = ProjectService(db_session)
        
        projects = service.get_projects_by_user(user_id=sample_user.user_id)
        
        assert len(projects) == 2
        assert all(p.user_id == sample_user.user_id for p in projects)

    def test_get_active_projects(self, db_session: Session, sample_user, sample_project, closed_project):
        """Test: obtener solo proyectos activos"""
        service = ProjectService(db_session)
        
        projects = service.get_active_projects(user_id=sample_user.user_id)
        
        assert len(projects) == 1
        assert projects[0].project_id == sample_project.project_id
        assert projects[0].project_is_closed is False

    def test_get_closed_projects(self, db_session: Session, sample_user, sample_project, closed_project):
        """Test: obtener solo proyectos cerrados"""
        service = ProjectService(db_session)
        
        projects = service.get_closed_projects(user_id=sample_user.user_id)
        
        assert len(projects) == 1
        assert projects[0].project_id == closed_project.project_id
        assert projects[0].project_is_closed is True

    def test_update_description(self, db_session: Session, sample_project, sample_user):
        """Test: actualizar descripción del proyecto"""
        service = ProjectService(db_session)
        
        new_description = "Updated description"
        project = service.update_description(
            project_id=sample_project.project_id,
            user_id=sample_user.user_id,
            new_description=new_description
        )
        
        assert project.project_description == new_description

    def test_advance_phase(self, db_session: Session, sample_project, sample_user):
        """Test: avanzar fase del proyecto"""
        service = ProjectService(db_session)
        
        initial_phase = sample_project.state
        project = service.advance_phase(
            project_id=sample_project.project_id,
            user_id=sample_user.user_id
        )
        
        assert project.state != initial_phase
        assert list(ProjectState).index(project.state) > list(ProjectState).index(initial_phase)

    def test_rollback_phase(self, db_session: Session, sample_project, sample_user):
        """Test: retroceder fase del proyecto"""
        service = ProjectService(db_session)
        
        # Primero avanzar
        service.advance_phase(
            project_id=sample_project.project_id,
            user_id=sample_user.user_id
        )
        
        # Luego retroceder
        project = service.rollback_phase(
            project_id=sample_project.project_id,
            user_id=sample_user.user_id
        )
        
        assert project.state == ProjectState.CREATED

    def test_close_project(self, db_session: Session, sample_project, sample_user):
        """Test: cerrar proyecto"""
        service = ProjectService(db_session)
        
        project = service.close_project(
            project_id=sample_project.project_id,
            user_id=sample_user.user_id
        )
        
        assert project.project_is_closed is True
        assert project.project_closed_at is not None

    def test_archive_project(self, db_session: Session, sample_project, sample_user):
        """Test: archivar proyecto"""
        service = ProjectService(db_session)
        
        project = service.archive_project(
            project_id=sample_project.project_id,
            user_id=sample_user.user_id
        )
        
        assert project.project_is_archived is True
        assert project.project_archived_at is not None


class TestProjectActivityService:
    """Tests para ProjectActivityService"""

    def test_create_activity(self, db_session: Session, sample_project, sample_user):
        """Test: crear actividad del proyecto"""
        service = ProjectActivityService(db_session)
        
        activity_data = ProjectActivityCreate(
            project_id=sample_project.project_id,
            user_id=sample_user.user_id,
            user_email=sample_user.user_email,
            project_action_type="TEST_ACTION",
            project_action_details="Test action details",
            project_action_metadata={"test": True}
        )
        
        activity = service.create_activity(data=activity_data)
        
        assert activity.project_id == sample_project.project_id
        assert activity.project_action_type == "TEST_ACTION"
        assert activity.project_action_metadata["test"] is True

    def test_get_project_activities(self, db_session: Session, sample_project, sample_activity):
        """Test: obtener actividades del proyecto"""
        service = ProjectActivityService(db_session)
        
        activities = service.get_project_activities(
            project_id=sample_project.project_id
        )
        
        assert len(activities) >= 1
        assert activities[0].project_id == sample_project.project_id

    def test_get_project_activities_filtered(self, db_session: Session, sample_project, sample_activity):
        """Test: filtrar actividades por tipo"""
        service = ProjectActivityService(db_session)
        
        activities = service.get_project_activities(
            project_id=sample_project.project_id,
            action_type="CREATED"
        )
        
        assert all(a.project_action_type == "CREATED" for a in activities)

    def test_get_user_recent_activities(self, db_session: Session, sample_user, sample_activity):
        """Test: obtener actividades recientes del usuario"""
        service = ProjectActivityService(db_session)
        
        activities = service.get_user_recent_activities(
            user_id=sample_user.user_id,
            limit=10
        )
        
        assert len(activities) >= 1
        assert all(a.user_id == sample_user.user_id for a in activities)
