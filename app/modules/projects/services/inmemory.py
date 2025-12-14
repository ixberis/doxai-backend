
# -*- coding: utf-8 -*-
"""
Servicios in-memory para pruebas de rutas del módulo Projects.
No tocan DB ni facades. Devuelven datos deterministas a partir de los IDs.
Autor: Ixchel Beristain
Fecha: 11/11/2025
"""

from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional
from uuid import UUID
from types import SimpleNamespace
from decimal import Decimal

from app.modules.projects.enums import ProjectState, ProjectStatus


class InMemoryProjectsQueryService:
    """Implementa solo lo que las rutas usan en tests."""

    def __init__(self, default_user_id: Optional[UUID] = None):
        self.default_user_id = default_user_id or UUID("00000000-0000-0000-0000-000000000001")

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    def get_project_by_id(self, project_id: UUID) -> Dict[str, Any]:
        now = self._now()
        # El test espera que el id devuelto sea EXACTAMENTE el del path
        return {
            "id": project_id,
            "project_id": project_id,
            "user_id": self.default_user_id,
            "user_email": "test@example.com",
            "project_name": "Test Project",
            "project_slug": f"proj-{str(project_id)[:8]}",
            "state": ProjectState.CREATED.value,
            "status": ProjectStatus.IN_PROCESS.value,
            "created_at": now - timedelta(days=1),
            "updated_at": now,
            "project_description": "Synthetic project for route tests",
            "ready_at": None,
            "archived_at": None,
        }

    def get_project_by_slug(self, slug: str) -> Dict[str, Any]:
        now = self._now()
        return {
            "id": UUID("00000000-0000-0000-0000-000000000099"),
            "project_id": UUID("00000000-0000-0000-0000-000000000099"),
            "user_id": self.default_user_id,
            "user_email": "test@example.com",
            "project_name": "Test Project by Slug",
            "project_slug": slug,
            "state": ProjectState.CREATED.value,
            "status": ProjectStatus.IN_PROCESS.value,
            "created_at": now - timedelta(days=1),
            "updated_at": now,
            "project_description": "Synthetic project for route tests",
            "ready_at": None,
            "archived_at": None,
        }

    def list_projects_by_user(
        self,
        user_id: str,
        state: Optional[str] = None,
        status: Optional[str] = None,
        include_total: bool = False,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        p = self.get_project_by_id(UUID("00000000-0000-0000-0000-000000000001"))
        if include_total:
            return [p], 1
        return ([p], 1)

    def list_ready_projects(
        self,
        user_id: str,
        include_total: bool = False,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        now = self._now()
        p = {
            "id": UUID("00000000-0000-0000-0000-000000000002"),
            "project_id": UUID("00000000-0000-0000-0000-000000000002"),
            "user_id": user_id,
            "user_email": "test@example.com",
            "project_name": "Ready Project",
            "project_slug": "ready-proj",
            "state": ProjectState.READY.value,
            "status": ProjectStatus.IN_PROCESS.value,
            "created_at": now - timedelta(days=2),
            "updated_at": now,
            "ready_at": now - timedelta(hours=1),
            "archived_at": None,
            "project_description": "Ready project for tests",
        }
        return [p], 1

    def list_files(
        self,
        project_id: UUID,
        user_id: str,
        include_total: bool = False,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        items = [{
            "id": UUID("11111111-1111-1111-1111-111111111111"),
            "project_id": project_id,
            "filename": "doc.pdf",
            "path": "/files/doc.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 12345,
            "checksum": "abc123",
            "validated": True,
            "created_at": self._now() - timedelta(hours=3),
        }]
        return items, len(items)

    def list_actions(self, project_id: UUID, limit: int = 20, offset: int = 0):
        items = [{
            "id": UUID("22222222-2222-2222-2222-222222222222"),
            "project_id": project_id,
            "action_type": "update",
            "action_details": {"field": "name", "old": "A", "new": "B"},
            "created_at": self._now() - timedelta(hours=2),
        }]
        return items, len(items)

    def list_file_events(
        self,
        project_id: UUID,
        file_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ):
        now = self._now()
        items = [{
            "id": UUID("33333333-3333-3333-3333-333333333333"),
            "project_file_event_log_id": UUID("33333333-3333-3333-3333-333333333333"),
            "project_id": project_id,
            "project_file_id": file_id or UUID("11111111-1111-1111-1111-111111111111"),
            "project_file_id_snapshot": file_id or UUID("11111111-1111-1111-1111-111111111111"),
            "user_id": UUID("00000000-0000-0000-0000-000000000099"),
            "user_email": "test@example.com",
            "event_type": event_type or "uploaded",
            "event_details": {"action": "test_upload"},
            "project_file_name_snapshot": "test.pdf",
            "project_file_path_snapshot": "/files/test.pdf",
            "project_file_size_kb_snapshot": Decimal("123.45"),
            "project_file_checksum_snapshot": "abc123def456",
            "event_created_at": now - timedelta(hours=4),
        }]
        return items, len(items)


class InMemoryProjectsCommandService:
    """Implementa solo lo que las rutas usan en tests (update/delete/status/state/archive)."""

    def __init__(self):
        # simulamos un pequeño "almacén" de proyectos tocados durante la sesión del test
        self._store: dict[UUID, Dict[str, Any]] = {}

    def create_project(
        self,
        user_id: str,
        user_email: str,
        project_name: str,
        project_slug: str,
        project_description: Optional[str] = None
    ) -> Dict[str, Any]:
        project_id = UUID("44444444-4444-4444-4444-444444444444")
        now = datetime.now(timezone.utc)
        p = {
            "id": project_id,
            "project_id": project_id,
            "user_id": user_id,
            "user_email": user_email,
            "project_name": project_name,
            "project_slug": project_slug,
            "project_description": project_description,
            "state": ProjectState.CREATED.value,
            "status": ProjectStatus.IN_PROCESS.value,
            "created_at": now,
            "updated_at": now,
            "ready_at": None,
            "archived_at": None,
        }
        self._store[project_id] = p
        return p

    def update_project(
        self,
        project_id: UUID,
        user_id: str,
        user_email: str,
        **kwargs
    ) -> Dict[str, Any]:
        p = self._store.get(project_id) or InMemoryProjectsQueryService(UUID(user_id) if isinstance(user_id, str) else user_id).get_project_by_id(project_id)
        d = dict(p)
        for k, v in kwargs.items():
            if v is not None:
                d[k] = v
        d["updated_at"] = datetime.now(timezone.utc)
        self._store[project_id] = d
        return d

    def delete(self, project_id: UUID, user_id: str, user_email: str) -> bool:
        self._store.pop(project_id, None)
        return True

    def change_status(
        self,
        project_id: UUID,
        user_id: str,
        user_email: str,
        new_status: ProjectStatus
    ) -> Dict[str, Any]:
        p = self._store.get(project_id) or InMemoryProjectsQueryService(UUID(user_id) if isinstance(user_id, str) else user_id).get_project_by_id(project_id)
        d = dict(p)
        d["status"] = new_status.value if hasattr(new_status, "value") else str(new_status)
        d["updated_at"] = datetime.now(timezone.utc)
        self._store[project_id] = d
        return d

    def transition_state(
        self,
        project_id: UUID,
        user_id: str,
        user_email: str,
        to_state: ProjectState
    ) -> Dict[str, Any]:
        p = self._store.get(project_id) or InMemoryProjectsQueryService(UUID(user_id) if isinstance(user_id, str) else user_id).get_project_by_id(project_id)
        d = dict(p)
        d["state"] = to_state.value if hasattr(to_state, "value") else str(to_state)
        d["updated_at"] = datetime.now(timezone.utc)
        self._store[project_id] = d
        return d

    def archive(self, project_id: UUID, user_id: str, user_email: str) -> Dict[str, Any]:
        return self.transition_state(project_id, user_id, user_email, ProjectState.ARCHIVED)

    def add_file(
        self,
        project_id: UUID,
        user_id: str,
        user_email: str,
        path: str,
        filename: str,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        checksum: Optional[str] = None
    ):
        """Devuelve objeto con atributos .id y .path para que las rutas puedan acceder a ellos."""
        file_id = UUID("55555555-5555-5555-5555-555555555555")
        return SimpleNamespace(
            id=file_id,
            project_id=project_id,
            path=path,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
        )

    def validate_file(self, file_id: UUID, user_id: str, user_email: str):
        """Devuelve objeto con atributo .id"""
        return SimpleNamespace(id=file_id, validated=True)

    def move_file(
        self,
        file_id: UUID,
        user_id: str,
        user_email: str,
        new_path: str
    ):
        """Devuelve objeto con atributos .id y .path"""
        return SimpleNamespace(id=file_id, path=new_path)

    def delete_file(self, file_id: UUID, user_id: str, user_email: str) -> bool:
        return True
# Fin del archivo backend/app/modules/projects/services/inmemory.py
