
# backend/tests/modules/projects/facades/test_project_file_facade_ops_contracts.py

from uuid import uuid4

def test_project_file_facade_add_and_move_calls_ops(monkeypatch):
    # Importamos el módulo del facade para inyectar su dependencia 'files'
    from app.modules.projects.facades import project_file_facade as pff
    from app.modules.projects.facades.project_file_facade import ProjectFileFacade

    called = {"add": False, "move": False}

    class FilesStub:
        @staticmethod
        def add_file(db, audit, *, project_id, path, mime_type, size_bytes, filename, user_id, user_email, checksum=None, **kwargs):
            called["add"] = True
            assert path.endswith(".pdf")
            assert filename == "demo.pdf"
            # Return ProjectFile-like object
            class FakeFile:
                def __init__(self):
                    self.id = uuid4()
                    self.project_id = project_id
                    self.path = path
                    self.checksum = checksum
            return FakeFile()

        @staticmethod
        def move_file(db, audit, *, file_id, user_id, user_email, new_path, **kwargs):
            called["move"] = True
            assert new_path.endswith(".pdf")
            # Return ProjectFile-like object
            class FakeFile:
                def __init__(self):
                    self.id = file_id
                    self.path = new_path
            return FakeFile()

    # Inyectamos el stub directamente en el módulo del facade
    monkeypatch.setattr(pff, "files", FilesStub, raising=True)

    facade = ProjectFileFacade(db=object())
    pid = uuid4()

    # add_file: todos keywords
    added_file = facade.add_file(
        project_id=pid,
        path="input/demo.pdf",
        filename="demo.pdf",
        mime_type="application/pdf",
        size_bytes=123,
        user_id=uuid4(),
        user_email="user@example.com",
    )

    # move_file: usa file_id y new_path como keywords
    facade.move_file(
        file_id=added_file.id,
        new_path="input/demo_v2.pdf",
        user_id=uuid4(),
        user_email="user@example.com",
    )

    assert called["add"] and called["move"]

# Fin del archivo backend/tests/modules/projects/facades/Test_project_file_facade_ops_contracts.py