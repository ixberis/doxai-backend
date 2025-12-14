
# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/queries.py

Rutas de solo lectura: listados de proyectos, auditoría y eventos de archivos.

Ajuste 10/11/2025:
- Agrega paginación por cursor opcional en GET /{project_id}/file-events
  (after_created_at, after_id) con fallback a limit/offset.
- response_model_exclude_none=True en endpoints de lectura.
- Mantiene contratos existentes y compatibilidad con tests.

Autor: Ixchel Beristain
Fecha de actualización: 10/11/2025
"""
from uuid import UUID
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import datetime

# Servicios y esquemas
from app.modules.projects.services import ProjectsQueryService
from app.modules.projects.routes.deps import get_projects_query_service
from app.modules.projects.schemas import (
    ProjectListResponse,
    ProjectRead,
)
from app.modules.projects.schemas.project_file_event_log_schemas import (
    ProjectFileEventLogListResponse,
)
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent

# Dependencias
from app.modules.auth.services import get_current_user

router = APIRouter(tags=["projects:queries"])

# ---------------------------------------------------------------------------
# Helper universal para user_id/email
# ---------------------------------------------------------------------------
def _uid_email(u):
    # acepta objeto o dict
    user_id = getattr(u, "user_id", None) or getattr(u, "id", None)
    email = getattr(u, "email", None)
    if user_id is None and isinstance(u, dict):
        user_id = u.get("user_id") or u.get("id")
        email = email or u.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth context")
    return user_id, email


# ---------------------------------------------------------------------------
# Listar proyectos del usuario
# ---------------------------------------------------------------------------
@router.get(
    "/",
    response_model=ProjectListResponse,
    response_model_exclude_none=True,
    summary="Listar proyectos del usuario (filtros opcionales)",
)
def list_projects_for_user(
    user_id: Optional[UUID] = None,
    state: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """
    Devuelve la lista de proyectos de un usuario autenticado.
    Si `user_id` no se provee, usa el ID del usuario actual.
    """
    uid, _ = _uid_email(user)
    target_user = user_id or uid

    items_or_tuple = q.list_projects_by_user(
        user_id=target_user,
        state=state,
        status=status,
        limit=limit,
        offset=offset,
        include_total=include_total,
    )

    if include_total:
        items, total = items_or_tuple
        return ProjectListResponse(
            success=True,
            items=[ProjectRead.model_validate(p) for p in items],
            total=total,
        )

    items = items_or_tuple
    return ProjectListResponse(
        success=True,
        items=[ProjectRead.model_validate(p) for p in items],
        total=len(items),
    )


# ---------------------------------------------------------------------------
# Listar proyectos en estado "ready"
# ---------------------------------------------------------------------------
@router.get(
    "/ready",
    response_model=ProjectListResponse,
    response_model_exclude_none=True,
    summary="Listar proyectos en estado 'ready'",
)
def list_ready_projects(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """
    Devuelve los proyectos del usuario en estado READY.
    """
    uid, _ = _uid_email(user)

    # Siempre pedir include_total=True para obtener tupla
    items, total = q.list_ready_projects(
        user_id=uid,
        limit=limit,
        offset=offset,
        include_total=True,
    )

    return ProjectListResponse(
        success=True,
        items=[ProjectRead.model_validate(p) for p in items],
        total=total if include_total else None,
    )


# ---------------------------------------------------------------------------
# Auditoría: acciones sobre un proyecto
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/actions",
    summary="Listar auditoría: acciones sobre proyecto",
    response_model_exclude_none=True,
)
def list_project_actions(
    project_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """
    Devuelve la bitácora de acciones ejecutadas sobre un proyecto.
    """
    uid, _ = _uid_email(user)
    items_total = q.list_actions(project_id=project_id, limit=limit, offset=offset)
    # Manejar retorno flexible: puede ser tupla (items, total) o solo items
    if isinstance(items_total, tuple):
        items, total = items_total
    else:
        items = items_total
        total = len(items) if items else 0
    return {"success": True, "items": [i.__dict__ if hasattr(i, '__dict__') else i for i in items], "total": total}


# ---------------------------------------------------------------------------
# Eventos de archivos (bitácora)
# ---------------------------------------------------------------------------

@router.get(
    "/{project_id}/file-events",
    response_model=ProjectFileEventLogListResponse,
    response_model_exclude_none=True,
    summary="Listar eventos de archivos de un proyecto",
)
def list_project_file_events(
    project_id: UUID,
    file_id: Optional[UUID] = Query(None),
    event_type: Optional[ProjectFileEvent] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),

    # AJUSTE: cursor UUID
    after_created_at: Optional[datetime] = Query(None),
    after_id: Optional[UUID] = Query(None),  # <-- corregido

    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """
    Devuelve la bitácora de eventos de archivos asociados a un proyecto.

    Filtros: file_id, event_type.
    Paginación:
      - Sin cursores: usa limit/offset (compatibilidad).
      - Con `after_created_at` y `after_id`: usa paginación por cursor (seek-based)
        para listas largas, con orden (event_created_at DESC, id DESC).
    """
    uid, _ = _uid_email(user)
    # Los services no aceptan include_total en list_file_events, solo limit/offset
    items_total = q.list_file_events(
        project_id=project_id,
        file_id=file_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    # Manejar retorno flexible: puede ser tupla (items, total) o solo items
    if isinstance(items_total, tuple):
        items, total = items_total
    else:
        items = items_total
        total = len(items) if items else 0

    return ProjectFileEventLogListResponse(
        success=True,
        items=items,
        total=total,
    )


# Fin del archivo backend/app/modules/projects/routes/queries.py

