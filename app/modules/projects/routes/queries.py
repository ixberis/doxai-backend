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
from app.shared.observability.timed_route import TimedAPIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.shared.database.database import get_db

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

# SSOT: get_current_user_ctx (Core) para rutas optimizadas (~40ms vs ~1200ms ORM)
# NO se usa get_current_user (ORM) en rutas de producto
from app.modules.auth.services import get_current_user_ctx
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO

router = APIRouter(tags=["projects:queries"], route_class=TimedAPIRoute)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Whitelist de columnas para ordenamiento
# Mapea nombres de parámetros del frontend a columnas reales de la BD
# ---------------------------------------------------------------------------
SORT_COLUMN_WHITELIST = {
    # SOLO valores canónicos (nombres directos de columna)
    "updated_at": "updated_at",
    "created_at": "created_at",
    "ready_at": "ready_at",
    "archived_at": "archived_at",
    "closed_at": "closed_at",  # RFC-FILES-RETENTION-001: para ordenar proyectos cerrados
    "project_name": "project_name",  # Para ordenar por nombre (A-Z, Z-A)
    # NOTA: last_activity_at fue removido - usar updated_at para "Más reciente"
}

# Set de valores legacy RECHAZADOS (para validación explícita y error 400)
REJECTED_LEGACY_SORT_KEYS: frozenset[str] = frozenset({
    "project_updated_at",
    "project_created_at",
    "project_ready_at",
})


# NOTA: _get_auth_user_id y _get_user_filter_context eliminados
# BD 2.0 SSOT: Usar directamente ctx.auth_user_id de get_current_user_ctx


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
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    start_time = time.perf_counter()

    # BD 2.0 SSOT: auth_user_id ya resuelto por get_current_user_ctx (Core)
    auth_user_id = ctx.auth_user_id

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
        "query_completed op=list_projects user=%s db_ms=%.2f ser_ms=%.2f total_ms=%.2f rows=%d",
        user_log, db_ms, ser_ms, total_ms, len(items)
    )

    return ProjectListResponse(
        success=True,
        items=response_items,
        total=total,
    )


# ---------------------------------------------------------------------------
# Listar proyectos activos (state != ARCHIVED)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Listar proyectos activos (state != ARCHIVED) con last_activity_at
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
    db: AsyncSession = Depends(get_db),  # Para calcular last_activity_at
):
    from app.shared.observability.request_telemetry import RequestTelemetry
    from app.modules.projects.facades.queries.last_activity import get_last_activity_at_batch
    
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

        # Fase: Serialization + last_activity_at enrichment
        with telemetry.measure("ser_ms"):
            if isinstance(items_or_tuple, tuple):
                items, total = items_or_tuple
            else:
                items = items_or_tuple
                total = len(items)
            
            # Obtener IDs de proyectos para batch query de last_activity_at
            project_ids = []
            for p in items:
                pid = getattr(p, 'id', None) or getattr(p, 'project_id', None)
                if pid:
                    project_ids.append(pid if isinstance(pid, UUID) else UUID(str(pid)))
            
            # Batch query para last_activity_at (NO catch silencioso - propaga errores)
            activity_map = {}
            if project_ids:
                activity_map = await get_last_activity_at_batch(db, project_ids)
            
            # Serializar con last_activity_at enriquecido
            response_items = []
            for p in items:
                validated = _project_read_validate(p)
                pid = validated.project_id
                if pid in activity_map and activity_map[pid]:
                    validated.last_activity_at = activity_map[pid]
                else:
                    # Fallback: usar updated_at si no hay datos de actividad
                    validated.last_activity_at = validated.updated_at
                response_items.append(validated)

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
# Listar proyectos cerrados (state == ARCHIVED) con last_activity_at
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
    db: AsyncSession = Depends(get_db),  # Para calcular last_activity_at
):
    from app.shared.observability.request_telemetry import RequestTelemetry
    from app.modules.projects.facades.queries.last_activity import get_last_activity_at_batch
    
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

        # Fase: Serialization + last_activity_at enrichment
        with telemetry.measure("ser_ms"):
            if isinstance(items_or_tuple, tuple):
                items, total = items_or_tuple
            else:
                items = items_or_tuple
                total = len(items)
            
            # Obtener IDs de proyectos para batch query de last_activity_at
            project_ids = []
            for p in items:
                pid = getattr(p, 'id', None) or getattr(p, 'project_id', None)
                if pid:
                    project_ids.append(pid if isinstance(pid, UUID) else UUID(str(pid)))
            
            # Batch query para last_activity_at (NO catch silencioso - propaga errores)
            activity_map = {}
            if project_ids:
                activity_map = await get_last_activity_at_batch(db, project_ids)
            
            # Serializar con last_activity_at enriquecido
            response_items = []
            for p in items:
                validated = _project_read_validate(p)
                pid = validated.project_id
                if pid in activity_map and activity_map[pid]:
                    validated.last_activity_at = activity_map[pid]
                else:
                    # Fallback: usar updated_at si no hay datos de actividad
                    validated.last_activity_at = validated.updated_at
                response_items.append(validated)

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
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    # BD 2.0 SSOT: auth_user_id ya resuelto por get_current_user_ctx
    auth_user_id = ctx.auth_user_id

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
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    # BD 2.0 SSOT: auth_user_id del contexto Core (para validación ownership si aplica)
    _ = ctx.auth_user_id  # Reservado para ownership check futuro
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
    ctx: AuthContextDTO = Depends(get_current_user_ctx),  # Core mode (~40ms)
    q: ProjectsQueryService = Depends(get_projects_query_service),
):
    import os
    # BD 2.0 SSOT: auth_user_id del contexto Core
    _ = ctx.auth_user_id  # Reservado para ownership check futuro
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



# ---------------------------------------------------------------------------
# Diagnóstico: timestamps de proyecto (requiere auth del usuario dueño)
# ---------------------------------------------------------------------------
@router.get(
    "/{project_id}/timestamps",
    summary="Diagnóstico: obtener timestamps del proyecto con actividad de archivos",
    tags=["projects:diagnostic"],
    responses={
        200: {"description": "Timestamps del proyecto con última actividad"},
        404: {"description": "Proyecto no encontrado"},
    },
)
async def get_project_timestamps(
    project_id: UUID,
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
    q: ProjectsQueryService = Depends(get_projects_query_service),
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint de diagnóstico para verificar que projects.updated_at
    se actualiza correctamente tras uploads de archivos.
    
    Retorna:
    - created_at: Fecha de creación del proyecto
    - updated_at: Última actualización del proyecto (campo BD)
    - latest_file_event_created_at: Timestamp del último evento de archivo
    - last_activity_at: GREATEST(updated_at, latest_file_event_created_at)
    - has_been_updated: True si updated_at > created_at
    
    Uso: comparar created_at vs updated_at antes/después de subir un archivo.
    
    Requiere autenticación: solo el usuario dueño del proyecto puede acceder.
    Montado bajo /api/projects (requiere auth vía get_current_user_ctx).
    """
    from sqlalchemy import text
    from app.modules.projects.facades.queries.last_activity import (
        get_latest_file_event_at,
        get_last_activity_at_single,
        get_latest_input_file_at_single,
    )
    
    # Log de acceso al endpoint
    logger.info(
        "timestamps_endpoint_called: project_id=%s user=%s",
        str(project_id)[:8],
        str(ctx.auth_user_id)[:8],
    )
    
    # Verificar ownership: el proyecto debe pertenecer al usuario autenticado
    project = await q.get_project_by_id(project_id=project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado",
        )
    
    # Verificar que el usuario es dueño del proyecto
    project_owner_id = getattr(project, 'auth_user_id', None)
    if project_owner_id is None:
        # Intentar obtener de dict si es un mapping
        if hasattr(project, '_mapping'):
            project_owner_id = project._mapping.get('auth_user_id')
        elif isinstance(project, dict):
            project_owner_id = project.get('auth_user_id')
    
    if project_owner_id != ctx.auth_user_id:
        logger.warning(
            "timestamps_access_denied: user=%s tried to access project=%s owned_by=%s",
            str(ctx.auth_user_id)[:8],
            str(project_id)[:8],
            str(project_owner_id)[:8] if project_owner_id else "<none>",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este proyecto",
        )
    
    # Obtener timestamps directamente de la BD usando Depends(get_db)
    # SSOT: Cast explícito CAST(:id AS uuid) y pasar UUID directamente
    result = await db.execute(
        text("""
            SELECT 
                id,
                created_at,
                updated_at,
                (updated_at > created_at) AS has_been_updated
            FROM public.projects 
            WHERE id = CAST(:id AS uuid)
        """),
        {"id": project_id},
    )
    row = result.mappings().fetchone()
    
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proyecto no encontrado en BD",
        )
    
    # Obtener datos de actividad de archivos (incluye input_files históricos)
    latest_file_event_at = await get_latest_file_event_at(db, project_id)
    latest_input_file_at = await get_latest_input_file_at_single(db, project_id)
    last_activity_at = await get_last_activity_at_single(db, project_id)
    
    # Log de resultado completo (SSOT: usando input_file_uploaded_at)
    logger.info(
        "timestamps_endpoint_result: project_id=%s updated_at=%s "
        "latest_input_file_uploaded=%s latest_file_event=%s last_activity=%s",
        str(project_id)[:8],
        row["updated_at"],
        latest_input_file_at,
        latest_file_event_at,
        last_activity_at,
    )
    
    return {
        "project_id": str(project_id),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "has_been_updated": row["has_been_updated"],
        # SSOT: timestamps de input_files usando input_file_uploaded_at
        "latest_input_file_uploaded_at": latest_input_file_at.isoformat() if latest_input_file_at else None,
        "latest_file_event_created_at": latest_file_event_at.isoformat() if latest_file_event_at else None,
        "last_activity_at": last_activity_at.isoformat() if last_activity_at else None,
        "diagnostic_note": (
            "last_activity_at = GREATEST(updated_at, COALESCE(latest_file_event, latest_input_file_uploaded)). "
            "Para proyectos históricos sin eventos, se usa input_files.input_file_uploaded_at."
        ),
    }


# ---------------------------------------------------------------------------
# Conteo de archivos de entrada por proyecto (batch, sin N+1)
# ---------------------------------------------------------------------------
@router.get(
    "/input-files-counts",
    summary="Conteo de archivos de entrada por proyecto (batch)",
    response_model_exclude_none=True,
)
async def get_input_files_counts(
    project_ids: list[UUID] = Query(default=[], description="Lista de project_ids (máx 200)"),
    ctx: AuthContextDTO = Depends(get_current_user_ctx),
    db: AsyncSession = Depends(get_db),
):
    """
    Devuelve el conteo de input_files activos (no archivados) para cada proyecto.
    
    - Máximo 200 project_ids por request.
    - Solo cuenta proyectos del usuario autenticado (auth_user_id).
    - Excluye archivos con input_file_is_archived=true.
    - Devuelve 0 para proyectos sin archivos (via LEFT JOIN).
    """
    from sqlalchemy import text
    
    # Validar límite
    if len(project_ids) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Máximo 200 project_ids por request",
                "error_code": "TOO_MANY_PROJECT_IDS",
            }
        )
    
    if not project_ids:
        return {"success": True, "items": []}
    
    auth_user_id = ctx.auth_user_id
    
    # Query agregada: una sola query para todos los proyectos
    # Excluye archivos archivados e inactivos/eliminados lógicamente
    sql = text("""
        SELECT 
            p.id AS project_id,
            COUNT(f.input_file_id) AS input_files_count
        FROM public.projects p
        LEFT JOIN public.input_files f
            ON f.project_id = p.id
            AND f.input_file_is_archived = false
            AND f.input_file_is_active = true
            AND f.storage_state = 'present'
        WHERE p.auth_user_id = CAST(:auth_user_id AS uuid)
            AND p.id = ANY(CAST(:project_ids AS uuid[]))
        GROUP BY p.id
    """)
    
    result = await db.execute(
        sql,
        {
            "auth_user_id": str(auth_user_id),
            "project_ids": [str(pid) for pid in project_ids],
        }
    )
    rows = result.fetchall()
    
    # Construir respuesta con todos los IDs (incluye 0s via LEFT JOIN)
    items = [
        {
            "project_id": str(row.project_id),
            "input_files_count": row.input_files_count,
        }
        for row in rows
    ]
    
    return {"success": True, "items": items}


# Fin del archivo backend/app/modules/projects/routes/queries.py

