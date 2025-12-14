
# backend/tests/modules/projects/facades/test_project_query_facade_contracts.py

from uuid import uuid4

def test_project_query_facade_lists_by_user(monkeypatch):
    # Importamos el módulo del facade para inyectar su dependencia 'queries'
    from app.modules.projects.facades import project_query_facade as pqf
    from app.modules.projects.facades.project_query_facade import ProjectQueryFacade

    class QueriesStub:
        @staticmethod
        def list_projects_by_user(db, user_id, include_total, limit, offset, state=None, status=None, **kwargs):
            assert include_total is True and limit == 10 and offset == 0
            return [{"id": "p1"}], 1

    # Inyectamos el stub directamente en el módulo del facade
    monkeypatch.setattr(pqf, "queries", QueriesStub, raising=True)

    facade = ProjectQueryFacade(db=object())
    rows1, total1 = facade.list_by_user(user_id=uuid4(), include_total=True, limit=10, offset=0)

    assert rows1 == [{"id": "p1"}] and total1 == 1

# Fin del archivo backend/tests/modules/projects/facades/test_project_query_facade_contracts.py