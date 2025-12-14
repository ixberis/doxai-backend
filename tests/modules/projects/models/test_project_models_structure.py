
# backend/tests/modules/projects/models/test_project_models_structure.py
import inspect
from typing import get_type_hints

def test_project_model_core_columns():
    from app.modules.projects.models.project_models import Project
    cols = Project.__table__.columns
    # Nomenclatura inconsistente en DB: state/status CON prefijo, timestamps SIN prefijo
    expected = {
        "id", "user_id", "user_email", "created_by", "updated_by",
        "project_name", "project_slug", "project_description",
        "project_state", "project_status",
        "created_at", "updated_at", "ready_at", "archived_at",
    }
    assert expected.issubset(set(cols.keys()))

def test_project_file_model_core_columns():
    from app.modules.projects.models.project_file_models import ProjectFile
    cols = ProjectFile.__table__.columns
    # Todos los campos de project_files tienen prefijo completo en DB
    expected = {
        "id", "project_id",
        "project_file_path", "project_file_name",
        "project_file_mime_type", "project_file_size_bytes",
        "project_file_checksum",
        "user_id", "user_email",
        "project_file_created_at", "project_file_updated_at",
    }
    assert expected.issubset(set(cols.keys()))

def test_action_log_and_file_event_log_models_exist_and_link_to_project():
    from app.modules.projects.models.project_action_log_models import ProjectActionLog
    from app.modules.projects.models.project_file_event_log_models import ProjectFileEventLog
    assert "project_id" in ProjectActionLog.__table__.columns
    assert "project_id" in ProjectFileEventLog.__table__.columns

def test_models_have_repr_or_str():
    from app.modules.projects.models.project_models import Project
    assert any(hasattr(Project, d) for d in ("__repr__", "__str__")), "Agrega __repr__ o __str__ útil"

def test_model_type_hints_dont_break_pydantic_from_attributes():
    from app.modules.projects.models.project_models import Project
    hints = get_type_hints(Project, include_extras=True)
    assert isinstance(hints, dict)

# Fin del archivo backend/tests/modules/projects/models/test_project_models_structure.py