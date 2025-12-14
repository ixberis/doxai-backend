# backend\tests\modules\projects\schemas\test_project_schemas.py

from datetime import datetime
from uuid import uuid4, UUID

def test_project_read_alias_id_to_project_id():
    from app.modules.projects.schemas.project_schemas import ProjectRead
    from app.modules.projects.enums import ProjectState, ProjectStatus

    # Fake ORM object con atributos que existen en el modelo real
    class ORMProject:
        def __init__(self):
            self.id = uuid4()
            self.user_id = uuid4()
            self.user_email = "user@example.com"
            self.project_name = "Demo"
            self.project_slug = "demo"
            self.project_description = "Desc"
            self.state = ProjectState.ready
            self.status = ProjectStatus.in_process
            self.created_at = datetime.utcnow()
            self.updated_at = datetime.utcnow()
            self.ready_at = None
            self.archived_at = None

    obj = ORMProject()
    dto = ProjectRead.model_validate(obj, from_attributes=True)
    assert isinstance(dto.project_id, UUID)
    assert dto.project_id == obj.id
    assert dto.project_name == obj.project_name
    assert dto.project_slug == obj.project_slug

def test_project_action_log_read_includes_optional_action_details():
    from app.modules.projects.schemas.project_action_log_schemas import ProjectActionLogRead
    from app.modules.projects.enums import ProjectActionType
    import uuid
    now = datetime.utcnow()

    any_action_type = next(iter(ProjectActionType))

    dto = ProjectActionLogRead(
        action_log_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        user_id=None,
        user_email=None,
        action_type=any_action_type,
        action_details="Algo pasó",
        action_metadata={"k": "v"},
        created_at=now,
    )
    assert dto.action_details == "Algo pasó"

def test_query_schemas_surfaces_expected_params():
    from app.modules.projects.schemas.project_query_schemas import (
        ProjectListByUserQuery,
        ProjectListReadyQuery,
        ProjectListFilesQuery,
    )
    q1 = ProjectListByUserQuery(user_id=uuid4(), include_total=True, limit=10, offset=0)
    q2 = ProjectListReadyQuery(include_total=False, limit=5, offset=5)
    q3 = ProjectListFilesQuery(project_id=uuid4(), include_total=True, limit=50, offset=0)
    assert q1.include_total is True and q2.include_total is False and q3.limit == 50

# Fin del archivo backend/tests/modules/projects/schemas/test_project_schemas.py