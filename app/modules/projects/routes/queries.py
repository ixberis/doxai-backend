# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/routes/queries.py

Rutas de solo lectura: listados de proyectos, auditoría y eventos de archivos.
Ahora async para compatibilidad con AsyncSession.

BD 2.0 SSOT Architecture (2026-01-10):
- auth_user_id (UUID): ÚNICO identificador de ownership en projects
- user_email: NO EXISTE en projects (columna eliminada en BD 2.0)
- Para obtener email, hacer JOIN con app_users via auth_user_id

IMPORTANTE:
NO hay fallback a user_email porque la columna projects.user_email
NO EXISTE en la base de datos BD 2.0.

Autor: Ixchel Beristain
Fecha de actualización: 2026-01-10 - BD 2.0 SSOT: eliminar user_email
"""
import time
import logging
from uuid import UUID
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from datetime import datetime

# Servicios y esquemas
from app.modules.projects.services import ProjectsQueryService
from app.modules.projects.routes.deps import get_projects_query_service, get_projects_query_service_timed
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

# Dependencias - SSOT: get_current_user_ctx (Core) para rutas optimizadas
# get_current_user (ORM) solo para rutas legacy que requieren objeto AppUser completo
from app.modules.auth.services import get_current_user_ctx, get_current_user
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO
from app.shared.auth_context import (
    extract_user_id,
    extract_auth_user_id,
)

router = APIRouter(tags=["projects:queries"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Whitelist de columnas para ordenamiento
# Mapea nombres de parámetros del frontend a columnas reales de la BD
# ---------------------------------------------------------------------------
SORT_COLUMN_WHITELIST = {
    # Legacy aliases (frontend antiguo) - loggear warning cuando se usen
    # SOLO valores canónicos (nombres directos de columna)
    "updated_at": "updated_at",
    "created_at": "created_at",
    "ready_at": "ready_at",
    "archived_at": "archived_at",
}

# Set de valores legacy RECHAZADOS (para validación explícita y error 400)
REJECTED_LEGACY_SORT_KEYS: frozenset[str] = frozenset({
    "project_updated_at",
    "project_created_at",
    "project_ready_at",
})


def _get_auth_user_id(user) -> UUID:
    """
    Extrae auth_user_id del usuario autenticado.

    BD 2.0 SSOT: auth_user_id es REQUERIDO. No hay fallback a email.

    Raises:
        HTTPException 401: Si el usuario no tiene auth_user_id
    """
    auth_user_id = extract_auth_user_id(user)
    
    if auth_user_id is None:
        logger.error(
            "auth_user_id_missing user_type=%s - BD 2.0 requiere auth_user_id",
            type(user).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": "Missing auth_user_id in auth context",
                "error_code": "AUTH_MISSING_UUID"
            }
        )
    
    return auth_user_id


def _get_user_filter_context(user: Any) -> tuple[Optional[UUID], Optional[str], bool]:
    """
    Extrae auth_user_id y email del usuario, determinando si es legacy.
    
    BD 2.0 SSOT: auth_user_id es el identificador canónico.
    - Si auth_user_id existe → is_legacy=False (usuario moderno)
    - Si auth_user_id es None → is_legacy=True (usuario legacy, usar email como fallback)
    
    Args:
        user: Objeto usuario con atributos auth_user_id y user_email
        
    Returns:
        Tuple de (auth_user_id, email, is_legacy)
    """
    auth_user_id = getattr(user, 'auth_user_id', None)
    email = getattr(user, 'user_email', None)
    is_legacy = auth_user_id is None
    
    if is_legacy:
        logger.warning(
            "legacy_user_email_filter_used email=%s",
            email
        )
    
    return auth_user_id, email, is_legacy


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
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    user=Depends(get_current_user),
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    start_time = time.perf_counter()

    # Fase: Auth Context (BD 2.0 SSOT)
    auth_start = time.perf_counter()
    auth_user_id = _get_auth_user_id(user)
    auth_ms = (time.perf_counter() - auth_start) * 1000

    # Fase: DB Query (BD 2.0: solo auth_user_id)
    db_start = time.perf_counter()
    items_or_tuple = await q.list_projects_by_auth_user_id(
        auth_user_id=auth_user_id,
        state=state,
        status=status_filter,
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
    user_log = str(auth_user_id)[:8] + "..."

    logger.info(
        "query_completed op=list_projects user=%s auth_ms=%.2f db_ms=%.2f ser_ms=%.2f total_ms=%.2f rows=%d",
        user_log, auth_ms, db_ms, ser_ms, total_ms, len(items)
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
    request: Request,
    ordenar_por: str = Query("updated_at", description="Columna para ordenar (canónico)"),
    asc: bool = Query(False, description="Orden ascendente (default: descendente)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms vs ~1200ms ORM)
    q: ProjectsQueryService = Depends(get_projects_query_service_timed),  # DB instrumentation
):
    from app.shared.observability.request_telemetry import RequestTelemetry
    
    telemetry = RequestTelemetry.create("projects.active-projects")
    
    try:
        # BD 2.0 SSOT: auth_user_id ya resuelto por get_current_user_ctx (Core)
        # NO se necesita fase auth extra - ctx ya está disponible con timings en request.state
        auth_user_id = ctx.auth_user_id

        # Fase: Validation (pre_ms) - RECHAZAR legacy con 400
        with telemetry.measure("pre_ms"):
            # Rechazar valores legacy explícitamente
            if ordenar_por in REJECTED_LEGACY_SORT_KEYS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"ordenar_por '{ordenar_por}' is legacy and rejected. Use canonical: {', '.join(SORT_COLUMN_WHITELIST.keys())}",
                        "error_code": "LEGACY_SORT_KEY_REJECTED",
                    }
                )
            
            if ordenar_por not in SORT_COLUMN_WHITELIST:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"ordenar_por debe ser uno de: {', '.join(SORT_COLUMN_WHITELIST.keys())}",
                        "error_code": "INVALID_SORT_COLUMN",
                    }
                )
            mapped_column = SORT_COLUMN_WHITELIST[ordenar_por]

        # Fase: DB Query (BD 2.0: solo auth_user_id, NO user_email)
        with telemetry.measure("db_ms"):
            items_or_tuple = await q.list_active_projects(
                auth_user_id=auth_user_id,
                order_by=mapped_column,
                asc=asc,
                limit=limit,
                offset=offset,
                include_total=include_total,
            )

        # Fase: Serialization
        with telemetry.measure("ser_ms"):
            if isinstance(items_or_tuple, tuple):
                items, total = items_or_tuple
            else:
                items = items_or_tuple
                total = len(items)
            response_items = [_project_read_validate(p) for p in items]

        # Set flags for observability
        telemetry.set_flag("rows", len(items))
        telemetry.set_flag("auth_user_id", str(auth_user_id)[:8] + "...")

        telemetry.finalize(request, status_code=200, result="success")

        return ProjectListResponse(
            success=True,
            items=response_items,
            total=total,
        )
        
    except HTTPException as e:
        # HTTPException: finalize con status real (validation_error o legacy_rejected)
        result_type = "legacy_rejected" if e.status_code == 400 else "http_error"
        telemetry.finalize(request, status_code=e.status_code, result=result_type)
        raise
    except Exception as e:
        telemetry.finalize(request, status_code=500, result="error")
        logger.exception("query_error op=list_active_projects error=%s", str(e))
        raise


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
    request: Request,
    ordenar_por: str = Query("updated_at", description="Columna para ordenar (canónico)"),
    asc: bool = Query(False, description="Orden ascendente (default: descendente)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms vs ~1200ms ORM)
    q: ProjectsQueryService = Depends(get_projects_query_service_timed),  # DB instrumentation
):
    from app.shared.observability.request_telemetry import RequestTelemetry
    
    telemetry = RequestTelemetry.create("projects.closed-projects")
    
    try:
        # BD 2.0 SSOT: auth_user_id ya resuelto por get_current_user_ctx (Core)
        auth_user_id = ctx.auth_user_id

        # Fase: Validation (pre_ms) - RECHAZAR legacy con 400
        with telemetry.measure("pre_ms"):
            # Rechazar valores legacy explícitamente
            if ordenar_por in REJECTED_LEGACY_SORT_KEYS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"ordenar_por '{ordenar_por}' is legacy and rejected. Use canonical: {', '.join(SORT_COLUMN_WHITELIST.keys())}",
                        "error_code": "LEGACY_SORT_KEY_REJECTED",
                    }
                )
            
            if ordenar_por not in SORT_COLUMN_WHITELIST:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"ordenar_por debe ser uno de: {', '.join(SORT_COLUMN_WHITELIST.keys())}",
                        "error_code": "INVALID_SORT_COLUMN",
                    }
                )
            mapped_column = SORT_COLUMN_WHITELIST[ordenar_por]

        # Fase: DB Query (BD 2.0: solo auth_user_id, NO user_email)
        with telemetry.measure("db_ms"):
            items_or_tuple = await q.list_closed_projects(
                auth_user_id=auth_user_id,
                order_by=mapped_column,
                asc=asc,
                limit=limit,
                offset=offset,
                include_total=include_total,
            )

        # Fase: Serialization
        with telemetry.measure("ser_ms"):
            if isinstance(items_or_tuple, tuple):
                items, total = items_or_tuple
            else:
                items = items_or_tuple
                total = len(items)
            response_items = [_project_read_validate(p) for p in items]

        # Set flags for observability
        telemetry.set_flag("rows", len(items))
        telemetry.set_flag("auth_user_id", str(auth_user_id)[:8] + "...")

        telemetry.finalize(request, status_code=200, result="success")

        return ProjectListResponse(
            success=True,
            items=response_items,
            total=total,
        )
        
    except HTTPException as e:
        # HTTPException: finalize con status real (validation_error o legacy_rejected)
        result_type = "legacy_rejected" if e.status_code == 400 else "http_error"
        telemetry.finalize(request, status_code=e.status_code, result=result_type)
        raise
    except Exception as e:
        telemetry.finalize(request, status_code=500, result="error")
        logger.exception("query_error op=list_closed_projects error=%s", str(e))
        raise


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
    # BD 2.0 SSOT: usar auth_user_id
    auth_user_id = _get_auth_user_id(user)

    result = await q.list_ready_projects(
        auth_user_id=auth_user_id,
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

