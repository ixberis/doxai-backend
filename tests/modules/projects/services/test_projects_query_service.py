# backend\tests\modules\projects\services\test_projects_query_service.py
import uuid
import pytest
import app.modules.projects.services.queries as queries_mod
from app.modules.projects.services import ProjectsQueryService
from app.modules.projects.enums import ProjectState, ProjectStatus
from datetime import datetime, timezone


@pytest.fixture
def fake_db():
    class _DB: ...
    return _DB()


@pytest.fixture
def ids():
    return {"project_id": uuid.uuid4(), "file_id": uuid.uuid4(), "user_id": uuid.uuid4()}


def test_get_project_by_id_and_slug(monkeypatch, mocker, fake_db, ids):
    facade_mock = mocker.MagicMock()
    project_obj = {"id": ids["project_id"], "slug": "alpha"}
    facade_mock.get_by_id.return_value = project_obj
    facade_mock.get_by_slug.return_value = project_obj
    monkeypatch.setattr(queries_mod, "ProjectQueryFacade", lambda db: facade_mock)
    svc = ProjectsQueryService(db=fake_db)

    assert svc.get_project_by_id(ids["project_id"]) == project_obj
    facade_mock.get_by_id.assert_called_once_with(ids["project_id"])

    assert svc.get_project_by_slug("alpha") == project_obj
    facade_mock.get_by_slug.assert_called_once_with("alpha")


def test_list_projects_by_user_with_and_without_total(monkeypatch, mocker, fake_db, ids):
    facade_mock = mocker.MagicMock()
    rows = [{"id": uuid.uuid4(), "state": ProjectState.created} for _ in range(3)]
    facade_mock.list_by_user.return_value = (rows, 42)
    monkeypatch.setattr(queries_mod, "ProjectQueryFacade", lambda db: facade_mock)

    svc = ProjectsQueryService(db=fake_db)

    data, total = svc.list_projects_by_user(
        user_id=ids["user_id"],
        state=ProjectState.created,
        status=None,
        limit=10,
        offset=20,
        include_total=True,
    )
    assert data == rows and total == 42
    facade_mock.list_by_user.assert_called_with(
        user_id=ids["user_id"],
        state=ProjectState.created,
        status=None,
        limit=10,
        offset=20,
        include_total=True,
    )

    facade_mock.list_by_user.reset_mock()
    facade_mock.list_by_user.return_value = rows
    data_only = svc.list_projects_by_user(
        user_id=ids["user_id"],
        state=None,
        status=ProjectStatus.in_process,
        limit=5,
        offset=0,
        include_total=False,
    )
    assert data_only == rows
    facade_mock.list_by_user.assert_called_with(
        user_id=ids["user_id"],
        state=None,
        status=ProjectStatus.in_process,
        limit=5,
        offset=0,
        include_total=False,
    )


def test_list_ready_projects(monkeypatch, mocker, fake_db, ids):
    facade_mock = mocker.MagicMock()
    rows = [{"id": uuid.uuid4(), "state": ProjectState.ready, "ready_at": datetime.now(timezone.utc)} for _ in range(2)]
    facade_mock.list_ready_projects.return_value = (rows, 2)
    monkeypatch.setattr(queries_mod, "ProjectQueryFacade", lambda db: facade_mock)

    svc = ProjectsQueryService(db=fake_db)

    data, total = svc.list_ready_projects(user_id=ids["user_id"], limit=50, offset=0, include_total=True)
    assert data == rows and total == 2
    facade_mock.list_ready_projects.assert_called_once_with(
        user_id=ids["user_id"], limit=50, offset=0, include_total=True
    )


def test_files_listing_and_count(monkeypatch, mocker, fake_db, ids):
    facade_mock = mocker.MagicMock()
    file_rows = [{"id": uuid.uuid4(), "project_id": ids["project_id"]} for _ in range(4)]
    facade_mock.list_files.return_value = (file_rows, 4)
    facade_mock.get_file_by_id.return_value = {"id": ids["file_id"], "project_id": ids["project_id"]}
    facade_mock.count_files_by_project.return_value = 4
    monkeypatch.setattr(queries_mod, "ProjectQueryFacade", lambda db: facade_mock)

    svc = ProjectsQueryService(db=fake_db)

    rows, total = svc.list_files(ids["project_id"], limit=100, offset=0, include_total=True)
    assert rows == file_rows and total == 4
    facade_mock.list_files.assert_called_once_with(ids["project_id"], limit=100, offset=0, include_total=True)

    one = svc.get_file_by_id(ids["file_id"])
    assert one["id"] == ids["file_id"]
    facade_mock.get_file_by_id.assert_called_once_with(ids["file_id"])

    count = svc.count_files_by_project(ids["project_id"])
    assert count == 4
    facade_mock.count_files_by_project.assert_called_once_with(ids["project_id"])


def test_audit_actions_and_file_events(monkeypatch, mocker, fake_db, ids):
    facade_mock = mocker.MagicMock()
    action_rows = [{"id": uuid.uuid4(), "type": "created"} for _ in range(3)]
    event_rows = [{"id": uuid.uuid4(), "event": "input_uploaded"} for _ in range(2)]
    facade_mock.list_actions.return_value = action_rows
    facade_mock.list_file_events.return_value = event_rows

    monkeypatch.setattr(queries_mod, "ProjectQueryFacade", lambda db: facade_mock)
    svc = ProjectsQueryService(db=fake_db)

    actions = svc.list_actions(ids["project_id"], action_type=None, limit=10, offset=0)
    assert actions == action_rows
    facade_mock.list_actions.assert_called_once_with(ids["project_id"], action_type=None, limit=10, offset=0)

    events = svc.list_file_events(ids["project_id"], file_id=ids["file_id"], event_type=None, limit=50, offset=5)
    assert events == event_rows
    facade_mock.list_file_events.assert_called_once_with(
        ids["project_id"], file_id=ids["file_id"], event_type=None, limit=50, offset=5
    )

# Fin del archivo backend/tests/modules/projects/services/test_projects_query_service.py
