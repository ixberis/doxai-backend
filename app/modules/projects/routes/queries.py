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
from typing import Optional
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
    extract_auth_user_id,  # SSOT UUID
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
        (auth_user_id, user_email, is_legacy) - auth_user_id o None, email, bool
    """
    # Intentar obtener auth_user_id (SSOT)
    auth_user_id = getattr(user, "auth_user_id", None)
    email = extract_user_email(user)
    
    if auth_user_id is not None:
        return (auth_user_id, email, False)
    
    # Fallback legacy: solo email
    if email:
        logger.warning(
            "legacy_user_email_filter_used user_email=%s - usuario sin auth_user_id",
            email[:3] + "***" if email else "unknown",
        )
        return (None, email, True)
    
    return (None, None, True)



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
    """
    Devuelve la lista de proyectos de un usuario autenticado.
    Usa user_email para filtrar (join key entre app_users y projects).
    """
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
    
    response_items = [ProjectRead.model_validate(p) for p in items]
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
    """
    Devuelve los proyectos activos (state != ARCHIVED) del usuario autenticado.
    
    SSOT: Filtra por auth_user_id (UUID) cuando está disponible.
    Legacy fallback: user_email si el usuario no tiene auth_user_id.
    
    Timing por fases:
    - auth_context: extracción de auth_user_id/email
    - validation: validación de parámetros
    - db_query: consulta a BD
    - serialization: transformación a response
    """
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
    items, total = await q.list_active_projects(
        auth_user_id=auth_user_id,  # SSOT UUID
        user_email=email if is_legacy else None,  # Solo para legacy
        order_by=mapped_column,
        asc=asc,
        limit=limit,
        offset=offset,
        include_total=include_total,
    )
    db_ms = (time.perf_counter() - db_start) * 1000
    
    # Fase: Serialization
    ser_start = time.perf_counter()
    response_items = [ProjectRead.model_validate(p) for p in items]
    ser_ms = (time.perf_counter() - ser_start) * 1000
    
    total_ms = (time.perf_counter() - start_time) * 1000
    user_log = str(auth_user_id)[:8] + "..." if auth_user_id else email
    
    # Logging por fases
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
    """
    Devuelve los proyectos cerrados/archivados (state == ARCHIVED) del usuario autenticado.
    
    SSOT: Filtra por auth_user_id (UUID) cuando está disponible.
    Legacy fallback: user_email si el usuario no tiene auth_user_id.
    
    Timing por fases:
    - auth_context: extracción de auth_user_id/email
    - validation: validación de parámetros
    - db_query: consulta a BD
    - serialization: transformación a response
    """
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
    items, total = await q.list_closed_projects(
        auth_user_id=auth_user_id,  # SSOT UUID
        user_email=email if is_legacy else None,  # Solo para legacy
        order_by=mapped_column,
        asc=asc,
        limit=limit,
        offset=offset,
        include_total=include_total,
    )
    db_ms = (time.perf_counter() - db_start) * 1000
    
    # Fase: Serialization
    ser_start = time.perf_counter()
    response_items = [ProjectRead.model_validate(p) for p in items]
    ser_ms = (time.perf_counter() - ser_start) * 1000
    
    total_ms = (time.perf_counter() - start_time) * 1000
    user_log = str(auth_user_id)[:8] + "..." if auth_user_id else email
    
    # Logging por fases
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
    """
    Devuelve los proyectos del usuario en estado READY.
    Usa user_email para filtrar.
    """
    email = extract_user_email(user)

    # Pedir include_total solo si se requiere
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
        items=[ProjectRead.model_validate(p) for p in items],
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
    """
    Devuelve la bitácora de acciones ejecutadas sobre un proyecto.
    """
    uid = extract_user_id(user)
    items = await q.list_actions(project_id=project_id, limit=limit, offset=offset)
    
    # Validar items: si son ORM objects, usar from_attributes=True
    validated_items = []
    for item in items:
        if hasattr(item, "__dict__") and hasattr(item, "__table__"):
            # ORM object
            validated_items.append(ProjectActionLogRead.model_validate(item, from_attributes=True))
        elif isinstance(item, dict):
            # Dict
            validated_items.append(ProjectActionLogRead.model_validate(item))
        else:
            # SimpleNamespace o similar con atributos
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

    # AJUSTE: cursor UUID
    after_created_at: Optional[datetime] = Query(None),
    after_id: Optional[UUID] = Query(None),

    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    """
    Devuelve la bitácora de eventos de archivos asociados a un proyecto.
    """
    import os
    uid = extract_user_id(user)
    strict_validation = os.getenv("STRICT_RESPONSE_VALIDATION", "0") == "1"
    
    # Helper para normalizar items (ORM → dict JSON-ready)
    def normalize_items(raw_items):
        """
        Normaliza items a formato JSON-ready compatible con response_model.
        - ORM objects: validar → model_dump(mode="json")
        - Dicts: normalizar tipos → validar si strict → model_dump(mode="json")
        - Todos los items terminan como dict JSON-ready.
        """
        from decimal import Decimal as DecimalType
        
        def normalize_dict(d: dict) -> dict:
            """
            Normaliza Decimal → str (schema usa Decimal, Pydantic serializa como str).
            Normaliza datetime → isoformat.
            """
            result = {}
            for k, v in d.items():
                if isinstance(v, DecimalType):
                    # Schema espera Decimal, JSON lo serializa como string
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
                # ORM object → validar con from_attributes → JSON-ready dict
                validated = ProjectFileEventLogRead.model_validate(item, from_attributes=True)
                normalized.append(validated.model_dump(mode="json"))
            elif isinstance(item, dict):
                # Dict → normalizar tipos primero
                item_normalized = normalize_dict(item)
                if strict_validation:
                    # Validar contra schema y convertir a JSON-ready
                    validated = ProjectFileEventLogRead.model_validate(item_normalized)
                    normalized.append(validated.model_dump(mode="json"))
                else:
                    # Ya está normalizado como dict JSON-ready
                    normalized.append(item_normalized)
            else:
                # SimpleNamespace o similar → validar → JSON-ready dict
                validated = ProjectFileEventLogRead.model_validate(item, from_attributes=True)
                normalized.append(validated.model_dump(mode="json"))
        return normalized
    
    # Cursor pagination: si ambos after_created_at y after_id vienen, usar seek
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
    
    # Fallback: limit/offset tradicional
    items_total = await q.list_file_events(
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

    normalized_items = normalize_items(items)
    return ProjectFileEventLogListResponse(
        success=True,
        items=normalized_items,
        total=total,
    )


# Fin del archivo backend/app/modules/projects/routes/queries.py
