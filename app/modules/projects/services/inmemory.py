
# -*- coding: utf-8 -*-
"""
Servicios in-memory para pruebas de rutas del módulo Projects.
No tocan DB ni facades. Devuelven datos deterministas a partir de los IDs.

Actualizado: 2025-12-27
- Convertido a async para compatibilidad con rutas async
- Añadido list_active_projects y list_closed_projects
- Añadido DummyFacade con list_file_events_seek para cursor pagination
- Corregido retorno de list_projects_by_user y list_ready_projects
- Corregido event_type para usar solo valores válidos del enum
- Normalización de datetimes a UTC-aware para evitar comparaciones naive/aware
- user_id ahora es int (no UUID)

Autor: Ixchel Beristain
"""

from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional, Sequence
from uuid import UUID
from types import SimpleNamespace
from decimal import Decimal

from app.modules.projects.enums import ProjectState, ProjectStatus
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent


# =============================================================================
# Helper para normalizar datetimes a UTC-aware
# =============================================================================

def _as_utc_aware(dt: Optional[datetime]) -> datetime:
    """
    Normaliza un datetime a UTC-aware.
    Si es None, retorna datetime.min con tzinfo=UTC.
    Si es naive, asume UTC y añade tzinfo.
    Si ya es aware, convierte a UTC.
    """
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# =============================================================================
# DummyFacade para cursor pagination (async)
# =============================================================================

class DummyFacade:
    """
    Facade dummy para simular list_file_events_seek en tests.
    El router llama q.facade.list_file_events_seek(...) para cursor pagination.
    Ahora async para compatibilidad con rutas async.
    """

    def __init__(self, default_user_id: int):
        self.default_user_id = default_user_id
        # Almacén de eventos para tests de cursor
        self._events: List[Dict[str, Any]] = []
        self._init_seed_events()

    def _init_seed_events(self):
        """
        Crea 3 eventos ordenables para probar cursor seek.
        
        Nota: user_id y user_email son Optional[UUID] y Optional[EmailStr] en el schema
        (ProjectFileEventLogRead líneas 54-60), por lo que None es válido para eventos
        generados por el sistema.
        """
        now = datetime.now(timezone.utc)
        base_project_id = UUID("00000000-0000-0000-0000-000000000001")
        base_file_id = UUID("11111111-1111-1111-1111-111111111111")

        # Usar solo event_types válidos del enum: uploaded, validated, moved, deleted
        # Incluir todos los campos requeridos por ProjectFileEventLogRead schema
        self._events = [
            {
                "id": UUID("33333333-3333-3333-3333-333333333331"),
                "project_id": base_project_id,
                "project_file_id": base_file_id,
                "project_file_id_snapshot": base_file_id,  # Required by schema
                "user_id": None,  # Sistema
                "user_email": None,
                "event_type": ProjectFileEvent.UPLOADED.value,  # "uploaded"
                "event_details": {"action": "upload_1"},
                "project_file_name_snapshot": "file1.pdf",
                "project_file_path_snapshot": "/files/file1.pdf",
                "project_file_size_kb_snapshot": Decimal("100.00"),
                "project_file_checksum_snapshot": "checksum1",
                "created_at": now - timedelta(hours=3),  # Más viejo
            },
            {
                "id": UUID("33333333-3333-3333-3333-333333333332"),
                "project_id": base_project_id,
                "project_file_id": base_file_id,
                "project_file_id_snapshot": base_file_id,
                "user_id": None,
                "user_email": None,
                "event_type": ProjectFileEvent.VALIDATED.value,  # "validated"
                "event_details": {"action": "validate_2"},
                "project_file_name_snapshot": "file2.pdf",
                "project_file_path_snapshot": "/files/file2.pdf",
                "project_file_size_kb_snapshot": Decimal("200.00"),
                "project_file_checksum_snapshot": "checksum2",
                "created_at": now - timedelta(hours=2),  # Medio
            },
            {
                "id": UUID("33333333-3333-3333-3333-333333333333"),
                "project_id": base_project_id,
                "project_file_id": base_file_id,
                "project_file_id_snapshot": base_file_id,
                "user_id": None,
                "user_email": None,
                "event_type": ProjectFileEvent.MOVED.value,  # "moved"
                "event_details": {"action": "move_3"},
                "project_file_name_snapshot": "file3.pdf",
                "project_file_path_snapshot": "/files/file3.pdf",
                "project_file_size_kb_snapshot": Decimal("300.00"),
                "project_file_checksum_snapshot": "checksum3",
                "created_at": now - timedelta(hours=1),  # Más nuevo
            },
        ]

    async def list_file_events_seek(
        self,
        project_id: UUID,
        *,
        after_created_at: Optional[datetime] = None,
        after_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> Sequence[Dict[str, Any]]:
        """
        Simula cursor seek: (created_at DESC, id DESC).
        Filtra eventos donde (created_at, id) < (after_created_at, after_id).
        Normaliza datetimes a UTC-aware para comparaciones seguras.
        """
        # Ordenar por (created_at DESC, id DESC) usando datetimes normalizados
        sorted_events = sorted(
            self._events,
            key=lambda e: (_as_utc_aware(e["created_at"]), e["id"]),
            reverse=True,
        )

        # Filtrar por event_type si se especifica
        if event_type is not None:
            sorted_events = [e for e in sorted_events if e.get("event_type") == event_type]

        # Aplicar cursor seek
        if after_created_at is not None and after_id is not None:
            # Normalizar cursor a UTC-aware
            cursor_created = _as_utc_aware(after_created_at)
            
            # Filtrar eventos estrictamente menores al cursor
            filtered = []
            for e in sorted_events:
                evt_created = _as_utc_aware(e["created_at"])
                evt_id = e["id"]
                # Comparación de tupla: (created_at, id) < (after_created_at, after_id)
                if (evt_created, evt_id) < (cursor_created, after_id):
                    filtered.append(e)
            sorted_events = filtered

        return sorted_events[:limit]

    async def list_file_events(
        self,
        project_id: UUID,
        file_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fallback offset-based para compatibilidad."""
        events = self._events[:]
        if event_type is not None:
            events = [e for e in events if e.get("event_type") == event_type]
        return events[offset : offset + limit]


# =============================================================================
# InMemoryProjectsQueryService (async)
# =============================================================================

class InMemoryProjectsQueryService:
    """Implementa solo lo que las rutas usan en tests. Ahora async."""

    def __init__(self, default_user_id: Optional[int] = None):
        self.default_user_id = default_user_id or 1
        # Facade dummy para cursor pagination
        self.facade = DummyFacade(self.default_user_id)
        # Proyectos semilla para tests
        self._projects = self._init_seed_projects()

    def _init_seed_projects(self) -> List[Dict[str, Any]]:
        """Crea proyectos semilla con diferentes estados. Todas las fechas son UTC-aware."""
        now = self._now()
        return [
            # Proyecto activo (CREATED)
            {
                "id": UUID("00000000-0000-0000-0000-000000000001"),
                "project_id": UUID("00000000-0000-0000-0000-000000000001"),
                "user_id": self.default_user_id,
                "user_email": "test@example.com",
                "project_name": "Active Project 1",
                "project_slug": "active-proj-1",
                "state": ProjectState.CREATED.value,
                "status": ProjectStatus.IN_PROCESS.value,
                "created_at": now - timedelta(days=5),
                "updated_at": now - timedelta(days=1),
                "ready_at": None,
                "archived_at": None,
                "project_description": "Active project for tests",
            },
            # Proyecto activo (READY)
            {
                "id": UUID("00000000-0000-0000-0000-000000000002"),
                "project_id": UUID("00000000-0000-0000-0000-000000000002"),
                "user_id": self.default_user_id,
                "user_email": "test@example.com",
                "project_name": "Ready Project",
                "project_slug": "ready-proj",
                "state": ProjectState.READY.value,
                "status": ProjectStatus.IN_PROCESS.value,
                "created_at": now - timedelta(days=3),
                "updated_at": now - timedelta(hours=6),
                "ready_at": now - timedelta(hours=2),
                "archived_at": None,
                "project_description": "Ready project for tests",
            },
            # Proyecto cerrado (ARCHIVED)
            {
                "id": UUID("00000000-0000-0000-0000-000000000003"),
                "project_id": UUID("00000000-0000-0000-0000-000000000003"),
                "user_id": self.default_user_id,
                "user_email": "test@example.com",
                "project_name": "Archived Project",
                "project_slug": "archived-proj",
                "state": ProjectState.ARCHIVED.value,
                "status": ProjectStatus.IN_PROCESS.value,
                "created_at": now - timedelta(days=10),
                "updated_at": now - timedelta(days=2),
                "ready_at": now - timedelta(days=5),
                "archived_at": now - timedelta(days=2),
                "project_description": "Archived project for tests",
            },
        ]

    @staticmethod
    def _now():
        """Retorna datetime actual UTC-aware."""
        return datetime.now(timezone.utc)

    async def get_project_by_id(self, project_id: UUID) -> Dict[str, Any]:
        # Buscar en proyectos semilla
        for p in self._projects:
            if p["id"] == project_id:
                return p
        # Fallback: generar proyecto sintético
        now = self._now()
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

    async def get_project_by_slug(self, slug: str) -> Dict[str, Any]:
        # Buscar en proyectos semilla
        for p in self._projects:
            if p["project_slug"] == slug:
                return p
        # Fallback
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

    async def list_projects_by_user(
        self,
        user_id=None,
        *,
        user_email: Optional[str] = None,
        state: Optional[str] = None,
        status: Optional[str] = None,
        include_total: bool = False,
        limit: int = 50,
        offset: int = 0,
    ):
        """
        Lista proyectos del usuario.
        Retorna: (items, total) si include_total=True, else items
        Acepta user_id o user_email para filtrado.
        """
        items = self._projects[:]
        if user_email is not None:
            items = [p for p in items if p.get("user_email") == user_email]
        elif user_id is not None:
            items = [p for p in items if p["user_id"] == user_id]
        if state is not None:
            items = [p for p in items if p["state"] == state]
        if status is not None:
            items = [p for p in items if p["status"] == status]

        total = len(items)
        items = items[offset : offset + limit]

        if include_total:
            return items, total
        return items

    async def list_ready_projects(
        self,
        user_id=None,
        *,
        user_email: Optional[str] = None,
        include_total: bool = False,
        limit: int = 50,
        offset: int = 0,
    ):
        """
        Lista proyectos en estado READY.
        Retorna: (items, total) si include_total=True, else items
        Acepta user_id o user_email para filtrado.
        """
        items = [p for p in self._projects if p["state"] == ProjectState.READY.value]
        if user_email is not None:
            items = [p for p in items if p.get("user_email") == user_email]
        elif user_id is not None:
            items = [p for p in items if p["user_id"] == user_id]

        total = len(items)
        items = items[offset : offset + limit]

        if include_total:
            return items, total
        return items

    async def list_active_projects(
        self,
        user_id=None,
        *,
        user_email: Optional[str] = None,
        auth_user_id: Optional[str] = None,
        order_by: str = "updated_at",
        asc: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Lista proyectos activos (state != ARCHIVED) con ordenamiento.
        Siempre retorna Tuple[items, total].
        Usa _as_utc_aware para comparaciones seguras de datetimes.
        Acepta user_id o user_email para filtrado.
        """
        items = [
            p for p in self._projects
            if p["state"] != ProjectState.ARCHIVED.value
            and (
                (user_email is not None and p.get("user_email") == user_email)
                or (user_id is not None and p["user_id"] == user_id)
                or (user_email is None and user_id is None)
            )
        ]

        # Ordenar con datetimes normalizados
        reverse = not asc
        items = sorted(
            items,
            key=lambda p: _as_utc_aware(p.get(order_by)),
            reverse=reverse,
        )

        total_count = len(items) if include_total else len(items[offset : offset + limit])
        items = items[offset : offset + limit]

        # Si include_total=False, total = len(items) de la página
        if not include_total:
            total_count = len(items)

        return items, total_count

    async def list_closed_projects(
        self,
        user_id=None,
        *,
        user_email: Optional[str] = None,
        auth_user_id: Optional[str] = None,
        order_by: str = "updated_at",
        asc: bool = False,
        limit: int = 50,
        offset: int = 0,
        include_total: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Lista proyectos cerrados (state == ARCHIVED) con ordenamiento.
        Siempre retorna Tuple[items, total].
        Usa _as_utc_aware para comparaciones seguras de datetimes.
        Acepta user_id o user_email para filtrado.
        """
        items = [
            p for p in self._projects
            if p["state"] == ProjectState.ARCHIVED.value
            and (
                (user_email is not None and p.get("user_email") == user_email)
                or (user_id is not None and p["user_id"] == user_id)
                or (user_email is None and user_id is None)
            )
        ]

        # Ordenar con datetimes normalizados
        reverse = not asc
        items = sorted(
            items,
            key=lambda p: _as_utc_aware(p.get(order_by)),
            reverse=reverse,
        )

        total_count = len(items) if include_total else len(items[offset : offset + limit])
        items = items[offset : offset + limit]

        # Si include_total=False, total = len(items) de la página
        if not include_total:
            total_count = len(items)

        return items, total_count

    async def list_files(
        self,
        project_id: UUID,
        user_id: int = None,
        include_total: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        items = [
            {
                "id": UUID("11111111-1111-1111-1111-111111111111"),
                "project_id": project_id,
                "filename": "doc.pdf",
                "path": "/files/doc.pdf",
                "mime_type": "application/pdf",
                "size_bytes": 12345,
                "checksum": "abc123",
                "validated": True,
                "created_at": self._now() - timedelta(hours=3),
            }
        ]
        return items, len(items)

    async def list_actions(
        self,
        project_id: UUID,
        action_type=None,
        limit: int = 100,
        offset: int = 0,
    ):
        """Retorna lista de acciones (no tupla) - consistente con service."""
        items = [
            {
                "id": UUID("22222222-2222-2222-2222-222222222222"),
                "project_id": project_id,
                "user_id": None,
                "user_email": None,
                "action_type": "updated",
                "action_details": "Updated field name",
                "action_metadata": {"field": "name", "old": "A", "new": "B"},
                "created_at": self._now() - timedelta(hours=2),
            }
        ]
        return items  # Solo lista, no tupla

    async def list_file_events(
        self,
        project_id: UUID,
        file_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        """Usa facade para consistencia."""
        items = await self.facade.list_file_events(
            project_id=project_id,
            file_id=file_id,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )
        return items, len(items)

    async def list_file_events_seek(
        self,
        project_id: UUID,
        *,
        after_created_at=None,
        after_id: Optional[UUID] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ):
        """Cursor-based pagination - delegates to facade."""
        return await self.facade.list_file_events_seek(
            project_id=project_id,
            after_created_at=after_created_at,
            after_id=after_id,
            event_type=event_type,
            limit=limit,
        )


# =============================================================================
# InMemoryProjectsCommandService (async)
# =============================================================================

class InMemoryProjectsCommandService:
    """Implementa solo lo que las rutas usan en tests (update/delete/status/state/archive). Ahora async."""

    def __init__(self):
        # simulamos un pequeño "almacén" de proyectos tocados durante la sesión del test
        self._store: dict[UUID, Dict[str, Any]] = {}

    async def create_project(
        self,
        user_id: int,
        user_email: str,
        project_name: str,
        project_slug: str,
        project_description: Optional[str] = None,
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

    async def update_project(
        self, project_id: UUID, user_id: int, user_email: str, **kwargs
    ) -> Dict[str, Any]:
        p = self._store.get(project_id) or (await InMemoryProjectsQueryService(user_id).get_project_by_id(project_id))
        d = dict(p)
        for k, v in kwargs.items():
            if v is not None:
                d[k] = v
        d["updated_at"] = datetime.now(timezone.utc)
        self._store[project_id] = d
        return d

    async def delete(self, project_id: UUID, user_id: int, user_email: str) -> bool:
        self._store.pop(project_id, None)
        return True

    async def change_status(
        self, project_id: UUID, user_id: int, user_email: str, new_status: ProjectStatus
    ) -> Dict[str, Any]:
        p = self._store.get(project_id) or (await InMemoryProjectsQueryService(user_id).get_project_by_id(project_id))
        d = dict(p)
        d["status"] = new_status.value if hasattr(new_status, "value") else str(new_status)
        d["updated_at"] = datetime.now(timezone.utc)
        self._store[project_id] = d
        return d

    async def transition_state(
        self, project_id: UUID, user_id: int, user_email: str, to_state: ProjectState
    ) -> Dict[str, Any]:
        p = self._store.get(project_id) or (await InMemoryProjectsQueryService(user_id).get_project_by_id(project_id))
        d = dict(p)
        d["state"] = to_state.value if hasattr(to_state, "value") else str(to_state)
        d["updated_at"] = datetime.now(timezone.utc)
        self._store[project_id] = d
        return d

    async def archive(self, project_id: UUID, user_id: int, user_email: str) -> Dict[str, Any]:
        return await self.transition_state(project_id, user_id, user_email, ProjectState.ARCHIVED)

    async def add_file(
        self,
        project_id: UUID,
        user_id: int,
        user_email: str,
        path: str,
        filename: str,
        mime_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        checksum: Optional[str] = None,
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

    async def validate_file(self, file_id: UUID, user_id: int, user_email: str):
        """Devuelve objeto con atributo .id"""
        return SimpleNamespace(id=file_id, validated=True)

    async def move_file(self, file_id: UUID, user_id: int, user_email: str, new_path: str):
        """Devuelve objeto con atributos .id y .path"""
        return SimpleNamespace(id=file_id, path=new_path)

    async def delete_file(self, file_id: UUID, user_id: int, user_email: str) -> bool:
        return True


# Fin del archivo backend/app/modules/projects/services/inmemory.py
