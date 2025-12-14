# backend\tests\modules\projects\services\test_projects_command_service.py
import uuid
import pytest
from datetime import datetime, timezone

import app.modules.projects.services.commands as commands_mod
from app.modules.projects.services import ProjectsCommandService
from app.modules.projects.enums import ProjectState, ProjectStatus


@pytest.fixture
def fake_db():
    class _DB: ...
    return _DB()


@pytest.fixture
def a_uuid():
    return uuid.uuid4()


@pytest.fixture
def user_ctx():
    return {"user_id": uuid.uuid4(), "user_email": "owner@example.com"}


def test_create_project_delegates_and_returns(monkeypatch, mocker, fake_db, user_ctx):
    facade_mock = mocker.MagicMock()
    facade_mock.create.return_value = {"id": uuid.uuid4(), "name": "Alpha"}
    monkeypatch.setattr(commands_mod, "ProjectFacade", lambda db: facade_mock)
    svc = ProjectsCommandService(db=fake_db)
    result = svc.create_project(
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
        project_name="Alpha",
        project_slug="alpha",
        project_description="Primer proyecto",
    )
    assert result == {"id": result["id"], "name": "Alpha"}
    facade_mock.create.assert_called_once_with(
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
        project_name="Alpha",
        project_slug="alpha",
        project_description="Primer proyecto",
    )


def test_update_project_partial_payload(monkeypatch, mocker, fake_db, a_uuid, user_ctx):
    facade_mock = mocker.MagicMock()
    facade_mock.update.return_value = {"id": a_uuid, "name": "Nuevo nombre", "description": None}
    monkeypatch.setattr(commands_mod, "ProjectFacade", lambda db: facade_mock)
    svc = ProjectsCommandService(db=fake_db)
    result = svc.update_project(
        a_uuid,
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
        project_name="Nuevo nombre",
    )
    assert result["id"] == a_uuid
    facade_mock.update.assert_called_once_with(
        a_uuid,
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
        project_name="Nuevo nombre",
    )


def test_change_status_delegates(monkeypatch, mocker, fake_db, a_uuid, user_ctx):
    facade_mock = mocker.MagicMock()
    facade_mock.change_status.return_value = {"id": a_uuid, "status": ProjectStatus.in_process}
    monkeypatch.setattr(commands_mod, "ProjectFacade", lambda db: facade_mock)
    svc = ProjectsCommandService(db=fake_db)
    res = svc.change_status(
        a_uuid,
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
        new_status=ProjectStatus.in_process,
    )
    assert res["status"] == ProjectStatus.in_process
    facade_mock.change_status.assert_called_once_with(
        a_uuid,
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
        new_status=ProjectStatus.in_process,
    )


def test_transition_state_valid_and_bubbles_errors(monkeypatch, mocker, fake_db, a_uuid, user_ctx):
    facade_mock = mocker.MagicMock()
    facade_mock.transition_state.return_value = {
        "id": a_uuid,
        "state": ProjectState.ready,
        "ready_at": datetime.now(timezone.utc),
    }
    monkeypatch.setattr(commands_mod, "ProjectFacade", lambda db: facade_mock)
    svc = ProjectsCommandService(db=fake_db)

    ok = svc.transition_state(
        a_uuid,
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
        to_state=ProjectState.ready,
    )
    assert ok["state"] == ProjectState.ready
    facade_mock.transition_state.assert_called_with(
        a_uuid,
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
        to_state=ProjectState.ready,
    )

    facade_mock.transition_state.side_effect = ValueError("Invalid transition")
    with pytest.raises(ValueError, match="Invalid transition"):
        svc.transition_state(
            a_uuid,
            user_id=user_ctx["user_id"],
            user_email=user_ctx["user_email"],
            to_state=ProjectState.created,
        )


def test_archive_and_delete_delegate(monkeypatch, mocker, fake_db, a_uuid, user_ctx):
    facade_mock = mocker.MagicMock()
    facade_mock.archive.return_value = {"id": a_uuid, "state": ProjectState.archived}
    facade_mock.delete.return_value = True
    monkeypatch.setattr(commands_mod, "ProjectFacade", lambda db: facade_mock)
    svc = ProjectsCommandService(db=fake_db)

    archived = svc.archive(a_uuid, user_id=user_ctx["user_id"], user_email=user_ctx["user_email"])
    assert archived["state"] == ProjectState.archived
    facade_mock.archive.assert_called_once_with(
        a_uuid,
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
    )

    deleted = svc.delete(a_uuid, user_id=user_ctx["user_id"], user_email=user_ctx["user_email"])
    assert deleted is True
    facade_mock.delete.assert_called_once_with(
        a_uuid,
        user_id=user_ctx["user_id"],
        user_email=user_ctx["user_email"],
    )

# Fin del archivo backend/tests/modules/projects/services/test_projects_command_service.py
