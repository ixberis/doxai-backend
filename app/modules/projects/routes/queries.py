# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/queries.py

Rutas de solo lectura: listados de proyectos, auditoría y eventos de archivos.
Ahora async para compatibilidad con AsyncSession.

SSOT Architecture (2025-01-07):
- auth_user_id (UUID): SSOT para ownership, coincide con projects.user_id
- user_email: LEGACY fallback, solo para usuarios sin auth_user_id (loggea warning)
- user_id (int): PK interna de app_users, NO usar para filtrar projects

Autor: Ixchel Beristain
Fecha de actualización: 2025-01-07 - SSOT auth_user_id + Timing por fases
"""
import time
import logging
from uuid import UUID
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from datetime import datetime

# Servicios y esquemas
from app.modules.projects.services import ProjectsQueryService
from app.modules.projects.routes.deps import get_projects_query_service
from app.modules.projects.schemas import (
    ProjectListResponse,
    ProjectRead,
    ProjectActionLogRead,
    ProjectActionLogListResponse,
)
from app.modules.projects.schemas.project_file_event_log_schemas import (
    ProjectFileEventLogListResponse,
    ProjectFileEventLogRead,
)
from app.modules.projects.enums.project_file_event_enum import ProjectFileEvent

# Dependencias
from app.modules.auth.services import get_current_user
from app.shared.auth_context import (
    extract_user_id,
    extract_user_email,
    extract_auth_user_id,  # SSOT UUID (puede no usarse directo aquí)
)

router = APIRouter(tags=["projects:queries"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Whitelist de columnas para ordenamiento
# Mapea nombres de parámetros del frontend a columnas reales de la BD
# ---------------------------------------------------------------------------
SORT_COLUMN_WHITELIST = {
    # Legacy aliases (frontend antiguo) - loggear warning cuando se usen
    "project_updated_at": "updated_at",
    "project_created_at": "created_at",
    "project_ready_at": "ready_at",
    # Nombres directos de columna (nuevos/preferidos)
    "updated_at": "updated_at",
    "created_at": "created_at",
    "ready_at": "ready_at",
    "archived_at": "archived_at",
}

# Set de aliases legacy para detectar uso
LEGACY_SORT_ALIASES = {"project_updated_at", "project_created_at", "project_ready_at"}


def _log_legacy_alias_warning(ordenar_por: str, operation: str, mapped_to: str):
    """Loggea warning cuando se usa un alias legacy de ordenamiento."""
    if ordenar_por in LEGACY_SORT_ALIASES:
        logger.warning(
            "legacy_sort_key_used op=%s key=%s mapped=%s",
            operation, ordenar_por, mapped_to
        )


def _get_user_filter_context(user) -> tuple:
    """
    Extrae contexto de filtrado del usuario para projects.

    SSOT: Preferir auth_user_id (UUID). Fallback a user_email solo para legacy.

    Returns:
        (auth_user_id, user_email, is_legacy) - auth_user_id o None, email o None, bool
    """
    auth_user_id = getattr(user, "auth_user_id", None)
    email = extract_user_email(user)

    if auth_user_id is not None:
        return (auth_user_id, email, False)

    if email:
        logger.warning(
            "legacy_user_email_filter_used user_email=%s - usuario sin auth_user_id",
            email[:3] + "***" if email else "unknown",
        )
        return (None, email, True)

    return (None, None, True)


def _normalize_project_item(item: Any) -> Any:
    """
    Normaliza un item devuelto por queries para que ProjectRead pueda validarlo.

    Maneja:
    - Niveles extra de anidación: [[{...}]] o [[[...]]] -> {...}
    - SQLAlchemy Row/RowMapping: item._mapping -> dict
    - ORM objects: se validan con from_attributes=True
    - Dict: se valida directo
    """
    # Unwrap iterativo (típico en mocks/rows): [[{...}]] / [[[...]]] / [(row,)]
    # Máximo 5 niveles para evitar loops raros.
    for _ in range(5):
        if isinstance(item, (list, tuple)) and len(item) == 1:
            item = item[0]
            continue
        break

    # Si después del unwrap sigue siendo list/tuple de dicts, dejamos evidencia clara
    # (no “adivinamos” tomando el primero si hay más de 1).
    if isinstance(item, (list, tuple)):
        # Caso común: [{...}] (lista de 1 dict) -> dict
        if len(item) == 1 and isinstance(item[0], dict):
            return item[0]
        # Si viene una lista de dicts >1, eso es un bug aguas arriba (service/repo)
        # pero evitamos 500 y dejamos error explícito.
        logger.error("projects_item_invalid_shape: got_list len=%d sample_type=%s", len(item), type(item[0]).__name__ if item else "empty")
        return item  # dejar que Pydantic falle con mensaje claro

    # SQLAlchemy Row: tiene ._mapping
    mapping = getattr(item, "_mapping", None)
    if mapping is not None:
        try:
            return dict(mapping)
        except Exception:
            pass

    return item

def _project_read_validate(item: Any) -> ProjectRead:
    """
    Valida un item como ProjectRead, soportando dict/ORM/Row y unwrap.
    """
    item = _normalize_project_item(item)

    if isinstance(item, dict):
        return ProjectRead.model_validate(item)

    # ORM / objetos con atributos
    return ProjectRead.model_validate(item, from_attributes=True)


# ---------------------------------------------------------------------------
# Listar proyectos del usuario
# ---------------------------------------------------------------------------
@router.get(
    "/",
    response_model=ProjectListResponse,
    response_model_exclude_none=True,
    summary="Listar proyectos del usuario (filtros opcionales)",
)
async def list_projects_for_user(
    state: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    start_time = time.perf_counter()

    # Fase: Auth Context
    auth_start = time.perf_counter()
    email = extract_user_email(user)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Missing email in auth context", "error_code": "AUTH_MISSING_EMAIL"}
        )
    auth_ms = (time.perf_counter() - auth_start) * 1000

    # Fase: DB Query
    db_start = time.perf_counter()
    items_or_tuple = await q.list_projects_by_user(
        user_email=email,
        state=state,
        status=status,
        limit=limit,
        offset=offset,
        include_total=include_total,
    )
    db_ms = (time.perf_counter() - db_start) * 1000

    # Fase: Serialization
    ser_start = time.perf_counter()
    if include_total:
        items, total = items_or_tuple
    else:
        items = items_or_tuple
        total = len(items)

    response_items = [_project_read_validate(p) for p in items]
    ser_ms = (time.perf_counter() - ser_start) * 1000

    total_ms = (time.perf_counter() - start_time) * 1000

    logger.info(
        "query_completed op=list_projects user=%s auth_ms=%.2f db_ms=%.2f ser_ms=%.2f total_ms=%.2f rows=%d",
        email, auth_ms, db_ms, ser_ms, total_ms, len(items)
    )

    return ProjectListResponse(
        success=True,
        items=response_items,
        total=total,
    )


# ---------------------------------------------------------------------------
# Listar proyectos activos (state != ARCHIVED)
# ---------------------------------------------------------------------------
@router.get(
    "/active-projects",
    response_model=ProjectListResponse,
    response_model_exclude_none=True,
    summary="Listar proyectos activos del usuario",
)
async def list_active_projects(
    ordenar_por: str = Query("project_updated_at", description="Columna para ordenar"),
    asc: bool = Query(False, description="Orden ascendente (default: descendente)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    start_time = time.perf_counter()

    # Fase: Auth Context (SSOT)
    auth_start = time.perf_counter()
    auth_user_id, email, is_legacy = _get_user_filter_context(user)

    if auth_user_id is None and email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Missing auth_user_id and email in auth context", "error_code": "AUTH_MISSING_IDENTITY"}
        )
    auth_ms = (time.perf_counter() - auth_start) * 1000

    # Fase: Validation
    if ordenar_por not in SORT_COLUMN_WHITELIST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"ordenar_por debe ser uno de: {', '.join(SORT_COLUMN_WHITELIST.keys())}",
                "error_code": "INVALID_SORT_COLUMN",
            }
        )

    mapped_column = SORT_COLUMN_WHITELIST[ordenar_por]
    _log_legacy_alias_warning(ordenar_por, "list_active_projects", mapped_column)

    # Fase: DB Query (SSOT: preferir auth_user_id)
    db_start = time.perf_counter()
    items_or_tuple = await q.list_active_projects(
        auth_user_id=auth_user_id,
        user_email=email if is_legacy else None,
        order_by=mapped_column,
        asc=asc,
        limit=limit,
        offset=offset,
        include_total=include_total,
    )
    db_ms = (time.perf_counter() - db_start) * 1000

    # Fase: Serialization (RETORNO FLEXIBLE)
    ser_start = time.perf_counter()
    if isinstance(items_or_tuple, tuple):
        items, total = items_or_tuple
    else:
        items = items_or_tuple
        total = len(items)

    response_items = [_project_read_validate(p) for p in items]
    ser_ms = (time.perf_counter() - ser_start) * 1000

    total_ms = (time.perf_counter() - start_time) * 1000
    user_log = str(auth_user_id)[:8] + "..." if auth_user_id else email

    if db_ms > 500:
        logger.warning(
            "query_slow op=list_active_projects phase=db_query user=%s duration_ms=%.2f rows=%d legacy=%s",
            user_log, db_ms, len(items), is_legacy
        )
    if ser_ms > 500:
        logger.warning(
            "query_slow op=list_active_projects phase=serialization user=%s duration_ms=%.2f rows=%d",
            user_log, ser_ms, len(items)
        )

    logger.info(
        "query_completed op=list_active_projects user=%s auth_ms=%.2f db_ms=%.2f ser_ms=%.2f total_ms=%.2f rows=%d legacy=%s",
        user_log, auth_ms, db_ms, ser_ms, total_ms, len(items), is_legacy
    )

    return ProjectListResponse(
        success=True,
        items=response_items,
        total=total,
    )


# ---------------------------------------------------------------------------
# Listar proyectos cerrados (state == ARCHIVED)
# ---------------------------------------------------------------------------
@router.get(
    "/closed-projects",
    response_model=ProjectListResponse,
    response_model_exclude_none=True,
    summary="Listar proyectos cerrados/archivados del usuario",
)
async def list_closed_projects(
    ordenar_por: str = Query("project_updated_at", description="Columna para ordenar"),
    asc: bool = Query(False, description="Orden ascendente (default: descendente)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    start_time = time.perf_counter()

    # Fase: Auth Context (SSOT)
    auth_start = time.perf_counter()
    auth_user_id, email, is_legacy = _get_user_filter_context(user)

    if auth_user_id is None and email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Missing auth_user_id and email in auth context", "error_code": "AUTH_MISSING_IDENTITY"}
        )
    auth_ms = (time.perf_counter() - auth_start) * 1000

    # Fase: Validation
    if ordenar_por not in SORT_COLUMN_WHITELIST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"ordenar_por debe ser uno de: {', '.join(SORT_COLUMN_WHITELIST.keys())}",
                "error_code": "INVALID_SORT_COLUMN",
            }
        )

    mapped_column = SORT_COLUMN_WHITELIST[ordenar_por]
    _log_legacy_alias_warning(ordenar_por, "list_closed_projects", mapped_column)

    # Fase: DB Query (SSOT: preferir auth_user_id)
    db_start = time.perf_counter()
    items_or_tuple = await q.list_closed_projects(
        auth_user_id=auth_user_id,
        user_email=email if is_legacy else None,
        order_by=mapped_column,
        asc=asc,
        limit=limit,
        offset=offset,
        include_total=include_total,
    )
    db_ms = (time.perf_counter() - db_start) * 1000

    # Fase: Serialization (RETORNO FLEXIBLE)
    ser_start = time.perf_counter()
    if isinstance(items_or_tuple, tuple):
        items, total = items_or_tuple
    else:
        items = items_or_tuple
        total = len(items)

    response_items = [_project_read_validate(p) for p in items]
    ser_ms = (time.perf_counter() - ser_start) * 1000

    total_ms = (time.perf_counter() - start_time) * 1000
    user_log = str(auth_user_id)[:8] + "..." if auth_user_id else email

    if db_ms > 500:
        logger.warning(
            "query_slow op=list_closed_projects phase=db_query user=%s duration_ms=%.2f rows=%d legacy=%s",
            user_log, db_ms, len(items), is_legacy
        )
    if ser_ms > 500:
        logger.warning(
            "query_slow op=list_closed_projects phase=serialization user=%s duration_ms=%.2f rows=%d",
            user_log, ser_ms, len(items)
        )

    logger.info(
        "query_completed op=list_closed_projects user=%s auth_ms=%.2f db_ms=%.2f ser_ms=%.2f total_ms=%.2f rows=%d legacy=%s",
        user_log, auth_ms, db_ms, ser_ms, total_ms, len(items), is_legacy
    )

    return ProjectListResponse(
        success=True,
        items=response_items,
        total=total,
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
async def list_ready_projects(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    email = extract_user_email(user)

    result = await q.list_ready_projects(
        user_email=email,
        limit=limit,
        offset=offset,
        include_total=include_total,
    )

    if include_total:
        items, total = result
    else:
        items = result
        total = len(items)

    return ProjectListResponse(
        success=True,
        items=[_project_read_validate(p) for p in items],
        total=total,
    )


# ---------------------------------------------------------------------------
# Auditoría: acciones sobre un proyecto
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/actions",
    response_model=ProjectActionLogListResponse,
    response_model_exclude_none=True,
    summary="Listar auditoría: acciones sobre proyecto",
)
async def list_project_actions(
    project_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    uid = extract_user_id(user)
    items = await q.list_actions(project_id=project_id, limit=limit, offset=offset)

    validated_items = []
    for item in items:
        if hasattr(item, "__dict__") and hasattr(item, "__table__"):
            validated_items.append(ProjectActionLogRead.model_validate(item, from_attributes=True))
        elif isinstance(item, dict):
            validated_items.append(ProjectActionLogRead.model_validate(item))
        else:
            validated_items.append(ProjectActionLogRead.model_validate(item, from_attributes=True))

    return ProjectActionLogListResponse(
        success=True,
        items=validated_items,
        total=len(validated_items),
    )


# ---------------------------------------------------------------------------
# Eventos de archivos (bitácora)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/file-events",
    response_model=ProjectFileEventLogListResponse,
    response_model_exclude_none=True,
    summary="Listar eventos de archivos de un proyecto",
)
async def list_project_file_events(
    project_id: UUID,
    file_id: Optional[UUID] = Query(None),
    event_type: Optional[ProjectFileEvent] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    after_created_at: Optional[datetime] = Query(None),
    after_id: Optional[UUID] = Query(None),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    import os
    uid = extract_user_id(user)
    strict_validation = os.getenv("STRICT_RESPONSE_VALIDATION", "0") == "1"

    def normalize_items(raw_items):
        from decimal import Decimal as DecimalType

        def normalize_dict(d: dict) -> dict:
            result = {}
            for k, v in d.items():
                if isinstance(v, DecimalType):
                    result[k] = str(v)
                elif isinstance(v, datetime):
                    result[k] = v.isoformat()
                elif isinstance(v, dict):
                    result[k] = normalize_dict(v)
                else:
                    result[k] = v
            return result

        normalized = []
        for item in raw_items:
            if hasattr(item, "__dict__") and hasattr(item, "__table__"):
                validated = ProjectFileEventLogRead.model_validate(item, from_attributes=True)
                normalized.append(validated.model_dump(mode="json"))
            elif isinstance(item, dict):
                item_normalized = normalize_dict(item)
                if strict_validation:
                    validated = ProjectFileEventLogRead.model_validate(item_normalized)
                    normalized.append(validated.model_dump(mode="json"))
                else:
                    normalized.append(item_normalized)
            else:
                validated = ProjectFileEventLogRead.model_validate(item, from_attributes=True)
                normalized.append(validated.model_dump(mode="json"))
        return normalized

    if after_created_at is not None and after_id is not None:
        items = await q.list_file_events_seek(
            project_id=project_id,
            after_created_at=after_created_at,
            after_id=after_id,
            event_type=event_type,
            limit=limit,
        )
        normalized_items = normalize_items(items)
        return ProjectFileEventLogListResponse(
            success=True,
            items=normalized_items,
            total=len(normalized_items),
        )

    items_total = await q.list_file_events(
        project_id=project_id,
        file_id=file_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    if isinstance(items_total, tuple):
        items, total = items_total
    else:
        items = items_total
        total = len(items) if items else 0

    normalized_items = normalize_items(items)
    return ProjectFileEventLogListResponse(
        success=True,
        items=normalized_items,
        total=total,
    )


# Fin del archivo backend/app/modules/projects/routes/queries.py

