# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/services/token_service.py

Utilidades de token para rutas protegidas de Auth.
Valida tipo y expiración de JWT, y expone dependencias para obtener el usuario actual.

SSOT Architecture (2025-01-07):
- JWT sub contiene auth_user_id (UUID), NO user_id (INT)
- _validate_and_get_user resuelve UUID primero, con fallback a INT para tokens legacy
- get_current_user_id retorna auth_user_id (UUID string)
- get_current_user retorna el objeto AppUser completo (retrocompatibilidad)
- get_current_user_ctx retorna AuthContextDTO (nuevo, optimizado Core)

ERROR CONTRACT (2026-01-13):
- Missing/invalid/expired token: 401 error="invalid_token"
- Invalid UUID sub: 401 error="invalid_user_id"
- User not found: 401 error="user_not_found"
- Inactive/locked user: 403 error="forbidden", message="User inactive or locked"

Instrumentación (2026-01-11):
- Auth dependency ahora mide jwt_decode_ms, user_lookup_ms, auth_dep_total_ms
- Timings guardados en request.state.auth_timings para RequestTelemetry

Autor: Ixchel Beristain
Actualizado: 2026-01-13 (Canonical error contract with dict details)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional
from uuid import UUID as PyUUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.enums import TokenType
from app.modules.auth.services.user_service import UserService
from app.modules.auth.schemas.auth_context_dto import AuthContextDTO
from app.shared.database.database import get_async_session
from app.shared.utils.security import verify_token_type

# HTTPBearer with auto_error=False to return 401 (not 403) when credentials missing
_bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def _require_credentials(creds: HTTPAuthorizationCredentials | None) -> HTTPAuthorizationCredentials:
    """
    Enforce credentials are present - raises 401 if missing.
    
    FastAPI's HTTPBearer with auto_error=True returns 403 on missing credentials,
    which violates RFC 7235. This helper returns 401 Unauthorized instead.
    
    Returns canonical error dict for frontend compatibility.
    """
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "Missing authentication credentials",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return creds

# Umbral para log INFO en auth dependency (default 500ms)
SLOW_AUTH_DEP_THRESHOLD_MS = float(os.getenv("SLOW_AUTH_DEP_THRESHOLD_MS", "500"))


def _finalize_auth_timings(
    request: Optional[Request],
    timings: dict,
    path: str,
    auth_user_id_masked: str,
) -> None:
    """Finaliza y guarda timings en request.state + log estructurado."""
    timings["auth_path"] = path
    
    if request is not None:
        try:
            request.state.auth_timings = timings
            request.state.auth_user_ctx_ms = timings["auth_dep_total_ms"]
            request.state.auth_db_ms = timings.get("auth_db_ms", 0)
        except Exception:
            pass
    
    # Log estructurado
    is_slow = timings["auth_dep_total_ms"] >= SLOW_AUTH_DEP_THRESHOLD_MS
    log_level = logging.INFO if is_slow else logging.DEBUG
    
    if logger.isEnabledFor(log_level):
        url_path = "unknown"
        if request is not None:
            try:
                url_path = str(request.url.path)
            except Exception:
                pass
        
        logger.log(
            log_level,
            "auth_dependency_breakdown path=%s auth_dep_total_ms=%.1f jwt_decode_ms=%.1f "
            "user_lookup_ms=%.1f auth_db_ms=%.1f mode=%s auth_user_id=%s",
            url_path,
            timings["auth_dep_total_ms"],
            timings.get("jwt_decode_ms", 0),
            timings.get("user_lookup_ms", 0),
            timings.get("auth_db_ms", 0),
            timings.get("auth_mode", "unknown"),
            auth_user_id_masked,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# NUEVO: get_current_user_ctx - Retorna AuthContextDTO (Core, optimizado)
# ═══════════════════════════════════════════════════════════════════════════════

async def _validate_and_get_user_ctx(
    token: str,
    db: AsyncSession,
    request: Optional[Request] = None,
    expected_type: str = "access",
    require_active_user: bool = True,
) -> AuthContextDTO:
    """
    Valida el token y retorna AuthContextDTO usando Core SQL.
    
    Optimizado para rutas que solo necesitan contexto auth (no AppUser completo).
    NO soporta legacy INT sub - solo UUID.
    
    NEW: Uses Redis cache for auth context (read-through with TTL).
    
    CANONICAL ERROR CONTRACT:
    - Invalid/expired token: 401 error="invalid_token"
    - Missing sub: 401 error="invalid_token"
    - Invalid UUID sub: 401 error="invalid_user_id"
    - User not found: 401 error="user_not_found"
    - Inactive/locked: 403 error="forbidden", message="User inactive or locked"
    
    Guarda timings en request.state.auth_timings.
    """
    t_start = time.perf_counter()
    timings = {
        "jwt_decode_ms": 0.0,
        "user_lookup_ms": 0.0,
        "auth_dep_total_ms": 0.0,
        "auth_db_ms": 0.0,
        "auth_mode": "core",
        "auth_ctx_cache_hit": False,
        "auth_ctx_cache_ms": 0.0,
    }
    auth_user_id_masked = "unknown"
    
    def _finalize(path: str):
        timings["auth_dep_total_ms"] = (time.perf_counter() - t_start) * 1000
        _finalize_auth_timings(request, timings, path, auth_user_id_masked)
    
    # ─── Fase: JWT Decode ───
    t_jwt_start = time.perf_counter()
    payload = verify_token_type(token, expected_type=expected_type)
    timings["jwt_decode_ms"] = (time.perf_counter() - t_jwt_start) * 1000
    
    if not payload:
        _finalize("invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "Invalid, expired, or incorrect token type",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        _finalize("missing_sub")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "Token missing 'sub' claim",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ─── Fase: Parse UUID ───
    try:
        auth_user_id = PyUUID(sub)
        auth_user_id_masked = str(auth_user_id)[:8] + "..."
    except ValueError:
        _finalize("invalid_uuid_sub")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_user_id",
                "message": "Invalid user id format (UUID required)",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # ─── Fase: Try Redis Cache First ───
    auth_context: Optional[AuthContextDTO] = None
    
    try:
        from app.shared.security.auth_context_cache import get_auth_context_cache
        
        cache = get_auth_context_cache()
        cached_mapping, cache_result = await cache.get_cached(auth_user_id)
        timings["auth_ctx_cache_ms"] = cache_result.duration_ms
        
        if cached_mapping:
            # Cache hit - construct DTO from cached data
            auth_context = AuthContextDTO.from_mapping(cached_mapping)
            timings["auth_ctx_cache_hit"] = True
            # user_lookup_ms stays 0 on cache hit (no DB lookup)
            timings["user_lookup_ms"] = 0.0
            timings["auth_db_ms"] = 0.0
            timings["auth_mode"] = "core_cached"
            
    except Exception as e:
        # Cache error - continue to DB lookup
        logger.debug("auth_ctx_cache_error: %s - falling back to DB", str(e))
    
    # ─── Fase: Core DB Lookup (if cache miss) ───
    if auth_context is None:
        t_lookup_start = time.perf_counter()
        
        user_service = UserService.with_session(db)
        auth_context, db_timings = await user_service.get_by_auth_user_id_core_ctx(auth_user_id)
        
        timings["user_lookup_ms"] = (time.perf_counter() - t_lookup_start) * 1000
        timings["auth_db_ms"] = db_timings.get("execute_ms", 0)
        
        if auth_context:
            # Cache the result for future requests (best-effort, silent)
            try:
                from app.shared.security.auth_context_cache import get_auth_context_cache
                cache = get_auth_context_cache()
                await cache.set_cached(auth_user_id, auth_context)
            except Exception:
                pass  # Ignore cache set errors - silent
    
    if not auth_context:
        _finalize("user_not_found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "user_not_found",
                "message": "User not found",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if require_active_user and not auth_context.is_active:
        _finalize("inactive_user")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": "User inactive or locked",
            },
        )
    
    _finalize("uuid_core" if not timings["auth_ctx_cache_hit"] else "uuid_cached")
    return auth_context


async def get_current_user_ctx(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
) -> AuthContextDTO:
    """
    Dependencia NUEVA: retorna AuthContextDTO (Core SQL, optimizado).
    
    Usar en rutas que solo necesitan contexto auth (user_id, auth_user_id, role, etc).
    NO soporta tokens legacy con sub INT - solo UUID.
    
    CANONICAL ERROR CONTRACT (emits dict details):
    - Missing credentials: 401 error="invalid_token"
    - Invalid/expired token: 401 error="invalid_token"
    - Invalid UUID sub: 401 error="invalid_user_id"
    - User not found: 401 error="user_not_found"
    - Inactive/locked user: 403 error="forbidden", message="User inactive or locked"
    
    Instrumentación: guarda timings en request.state.auth_timings.
    """
    validated_creds = _require_credentials(creds)
    expected_type = TokenType.access.value if hasattr(TokenType, "access") else "access"
    return await _validate_and_get_user_ctx(
        validated_creds.credentials,
        db,
        request=request,
        expected_type=expected_type,
        require_active_user=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY: get_current_user - Retorna AppUser (ORM, retrocompatibilidad)
# ═══════════════════════════════════════════════════════════════════════════════

async def _validate_and_get_user(
    token: str,
    db: AsyncSession,
    request: Optional[Request] = None,
    expected_type: str = "access",
    require_active_user: bool = True,
):
    """
    Valida el token y retorna AppUser COMPLETO usando ORM.
    
    Soporta tokens legacy con sub INT.
    Retorna AppUser real (no proxy).
    
    Guarda timings en request.state.auth_timings.
    """
    t_start = time.perf_counter()
    timings = {
        "jwt_decode_ms": 0.0,
        "user_lookup_ms": 0.0,
        "auth_dep_total_ms": 0.0,
        "auth_db_ms": 0.0,
        "auth_mode": "orm",
    }
    auth_user_id_masked = "unknown"
    
    def _finalize(path: str):
        timings["auth_dep_total_ms"] = (time.perf_counter() - t_start) * 1000
        _finalize_auth_timings(request, timings, path, auth_user_id_masked)
    
    # ─── Fase: JWT Decode ───
    t_jwt_start = time.perf_counter()
    payload = verify_token_type(token, expected_type=expected_type)
    timings["jwt_decode_ms"] = (time.perf_counter() - t_jwt_start) * 1000
    
    if not payload:
        _finalize("invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "Invalid, expired, or incorrect token type",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        _finalize("missing_sub")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_token",
                "message": "Token missing 'sub' claim",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_service = UserService.with_session(db)
    user = None
    
    # ─── Fase: User Lookup ───
    t_lookup_start = time.perf_counter()
    
    # SSOT: Intentar primero como UUID
    try:
        auth_user_id = PyUUID(sub)
        auth_user_id_masked = str(auth_user_id)[:8] + "..."
        user = await user_service.get_by_auth_user_id(auth_user_id)
    except ValueError:
        pass  # No es UUID, intentar como INT (legacy)
    
    # Fallback: sub es user_id INT (legacy transitorio)
    if not user:
        timings["auth_mode"] = "orm_legacy"
        try:
            user_id_int = int(sub)
            auth_user_id_masked = f"legacy_{user_id_int}"
            user = await user_service.get_by_id(user_id_int)
            
            if user:
                logger.warning(
                    "legacy_token_sub_int_used user_id=%s - migrando a auth_user_id UUID",
                    user_id_int,
                )
                # Fix legacy: generar auth_user_id si no existe
                if user.auth_user_id is None:
                    from uuid import uuid4
                    user.auth_user_id = uuid4()
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    logger.warning(
                        "legacy_user_missing_auth_user_id_fixed user_id=%s new_auth_user_id=%s",
                        user_id_int,
                        str(user.auth_user_id)[:8] + "...",
                    )
        except ValueError:
            pass
    
    timings["user_lookup_ms"] = (time.perf_counter() - t_lookup_start) * 1000

    if not user:
        _finalize("user_not_found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "user_not_found",
                "message": "User not found",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if require_active_user:
        if not await user_service.is_active(user):
            _finalize("inactive_user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": "User inactive or locked",
                },
            )

    _finalize("uuid" if timings["auth_mode"] == "orm" else "legacy_int")
    return user


async def get_current_user_id(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
) -> str:
    """
    Dependencia para rutas que requieren un token válido.
    Retorna auth_user_id (UUID como string) del usuario.
    
    Usa Core mode para optimización (via get_current_user_ctx).
    """
    validated_creds = _require_credentials(creds)
    ctx = await get_current_user_ctx(request, validated_creds, db)
    return str(ctx.auth_user_id)


async def get_optional_user_id(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
) -> Optional[str]:
    """
    Dependencia opcional: si hay token válido devuelve auth_user_id (UUID), 
    si no hay token o es inválido, devuelve None.
    """
    if creds is None:
        return None
    try:
        ctx = await get_current_user_ctx(request, creds, db)
        return str(ctx.auth_user_id)
    except HTTPException:
        return None


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_async_session),
):
    """
    RETROCOMPATIBILIDAD: devuelve el objeto AppUser COMPLETO (ORM).
    
    Usa ORM mode - más lento pero retorna AppUser real.
    Para rutas nuevas, preferir get_current_user_ctx (Core, más rápido).
    
    Instrumentación: guarda timings en request.state.auth_timings.
    """
    validated_creds = _require_credentials(creds)
    expected_type = TokenType.access.value if hasattr(TokenType, "access") else "access"
    return await _validate_and_get_user(
        validated_creds.credentials,
        db,
        request=request,
        expected_type=expected_type,
        require_active_user=True,
    )


__all__ = [
    "get_current_user_id",
    "get_optional_user_id",
    "get_current_user",
    "get_current_user_ctx",
    "AuthContextDTO",
]

# Fin del script backend/app/modules/auth/services/token_service.py
