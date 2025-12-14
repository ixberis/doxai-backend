
# backend/tests/modules/projects/facades/test_project_facade_create_mapping.py
from uuid import uuid4

def test_project_facade_create_maps_schema_fields_to_internal_names(monkeypatch):
    from app.modules.projects.facades.project_facade import ProjectFacade
    import app.modules.projects.facades.projects as projects_pkg

    captured = {}

    def fake_create(*, db, audit, user_id, user_email, name, slug, description):
        captured.update(dict(
            db=bool(db), audit=bool(audit),
            user_id=user_id, user_email=user_email,
            name=name, slug=slug, description=description
        ))
        return object()  # simulamos un Project

    # Parchear el símbolo que usa el facade (paquete 'projects', no el submódulo 'crud')
    monkeypatch.setattr(projects_pkg, "create", fake_create, raising=True)

    facade = ProjectFacade(db=object())  # db fake; no se usará porque interceptamos 'create'
    project = facade.create(
        user_id=uuid4(),
        user_email="user@example.com",
        project_name="Mi Proyecto",
        project_slug="mi-proyecto",
        project_description="Desc",
    )

    assert project is not None
    assert captured["name"] == "Mi Proyecto"
    assert captured["slug"] == "mi-proyecto"
    assert captured["description"] == "Desc"

# Fin del archivo backend/tests/modules/projects/facades/test_project_facade_create_mapping.py