# -*- coding: utf-8 -*-
"""
backend/app/modules/projects/services/touch_debouncer.py

Debounce de touch_project_updated_at usando Redis con TTL.

Evita múltiples actualizaciones de projects.updated_at durante operaciones
batch (como delete múltiple de archivos), ejecutando touch como máximo
una vez por ventana de tiempo por proyecto.

Implementación:
- Usa Redis SET NX EX para debounce atómico
- Best-effort: si Redis no está disponible, permite el touch (fail-open)
- Sin commits propios, delega transacción al caller
- Configurable via env var TOUCH_DEBOUNCE_WINDOW_SECONDS
- Expone métricas Prometheus (allowed/skipped/redis_error/redis_unavailable)

Autor: DoxAI
Fecha: 2026-01-23
Updated: 2026-01-23 - Added env var config + Prometheus metrics
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.services.touch import touch_project_updated_at
from app.shared.redis.client import get_async_redis_client

_logger = logging.getLogger("projects.touch_debouncer")

# Prefijo canónico para keys de debounce
DEBOUNCE_KEY_PREFIX = "doxai:touch_project"

# ---------------------------------------------------------------------------
# Configuración por env var
# ---------------------------------------------------------------------------
_DEFAULT_WINDOW_FALLBACK = 3  # Fallback si env var no existe o es inválida
_env_window_logged = False  # Para loguear warning solo una vez


def _get_default_window_seconds() -> int:
    """
    Obtiene la ventana de debounce desde env var TOUCH_DEBOUNCE_WINDOW_SECONDS.
    
    Returns:
        Valor de env var si es válido (int > 0), o 3 como fallback.
        Loguea warning una sola vez si el valor es inválido.
    """
    global _env_window_logged
    
    env_value = os.getenv("TOUCH_DEBOUNCE_WINDOW_SECONDS")
    
    if env_value is None:
        return _DEFAULT_WINDOW_FALLBACK
    
    try:
        parsed = int(env_value)
        if parsed <= 0:
            if not _env_window_logged:
                _logger.warning(
                    "touch_debounce_env_invalid: TOUCH_DEBOUNCE_WINDOW_SECONDS=%s "
                    "(must be > 0), using fallback=%d",
                    env_value,
                    _DEFAULT_WINDOW_FALLBACK,
                )
                _env_window_logged = True
            return _DEFAULT_WINDOW_FALLBACK
        return parsed
    except ValueError:
        if not _env_window_logged:
            _logger.warning(
                "touch_debounce_env_invalid: TOUCH_DEBOUNCE_WINDOW_SECONDS=%s "
                "(not an int), using fallback=%d",
                env_value,
                _DEFAULT_WINDOW_FALLBACK,
            )
            _env_window_logged = True
        return _DEFAULT_WINDOW_FALLBACK


# Ventana de debounce por defecto (segundos) - ahora configurable
DEFAULT_WINDOW_SECONDS = _get_default_window_seconds()


# ---------------------------------------------------------------------------
# Métricas Prometheus (lazy import para evitar circular dependencies)
# ---------------------------------------------------------------------------
def _inc_metric_allowed(reason: str) -> None:
    """Incrementa contador de touch permitido."""
    try:
        from app.modules.projects.metrics.collectors.touch_debounce_collectors import (
            inc_touch_allowed,
        )
        inc_touch_allowed(reason)
    except Exception:
        pass  # Never break caller flow


def _inc_metric_skipped(reason: str) -> None:
    """Incrementa contador de touch omitido."""
    try:
        from app.modules.projects.metrics.collectors.touch_debounce_collectors import (
            inc_touch_skipped,
        )
        inc_touch_skipped(reason)
    except Exception:
        pass


def _inc_metric_redis_error(reason: str) -> None:
    """Incrementa contador de error Redis."""
    try:
        from app.modules.projects.metrics.collectors.touch_debounce_collectors import (
            inc_touch_redis_error,
        )
        inc_touch_redis_error(reason)
    except Exception:
        pass


def _inc_metric_redis_unavailable(reason: str) -> None:
    """Incrementa contador de Redis no disponible."""
    try:
        from app.modules.projects.metrics.collectors.touch_debounce_collectors import (
            inc_touch_redis_unavailable,
        )
        inc_touch_redis_unavailable(reason)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Core debounce logic
# ---------------------------------------------------------------------------
async def _try_acquire_debounce_lock(
    redis_client: Any,
    project_id: UUID,
    reason: str,
    window_seconds: int,
) -> bool:
    """
    Intenta adquirir lock de debounce usando SET NX EX.
    
    Args:
        redis_client: Cliente Redis async
        project_id: UUID del proyecto
        reason: Motivo del touch (para key única por tipo de operación)
        window_seconds: TTL del lock en segundos
    
    Returns:
        True si se adquirió el lock (primera llamada en la ventana)
        False si ya existe lock (llamada duplicada en la ventana)
    """
    # Key canónica: doxai:touch_project:{project_id}:{reason}
    key = f"{DEBOUNCE_KEY_PREFIX}:{project_id}:{reason}"
    
    try:
        # SET key "1" NX EX window_seconds
        # NX = solo si no existe
        # EX = expiración en segundos
        result = await redis_client.set(
            key,
            "1",
            nx=True,
            ex=window_seconds,
        )
        
        # SET NX retorna True si se estableció, None/False si ya existía
        return result is True
        
    except Exception as e:
        _logger.warning(
            "touch_debounce_lock_error: project_id=%s reason=%s error=%s",
            str(project_id)[:8],
            reason,
            str(e),
        )
        # Error en Redis → fail-open (permitir touch) + metric
        _inc_metric_redis_error(reason)
        return True


async def touch_project_debounced(
    db: AsyncSession,
    project_id: UUID,
    *,
    reason: str = "unspecified",
    window_seconds: Optional[int] = None,
) -> bool:
    """
    Touch project.updated_at con debounce via Redis TTL.
    
    Ejecuta touch_project_updated_at como máximo una vez por ventana
    de tiempo por proyecto+reason.
    
    Args:
        db: Sesión async de base de datos
        project_id: UUID del proyecto a actualizar
        reason: Motivo del touch (para key única por tipo de operación)
        window_seconds: Ventana de debounce en segundos (default: env var o 3)
    
    Returns:
        True si se ejecutó el touch
        False si se omitió por debounce
        
    Note:
        Best-effort: si Redis no está disponible, ejecuta el touch (fail-open).
        No hace commit propio, delega al caller.
    """
    # Usar default configurable si no se especifica window_seconds
    effective_window = window_seconds if window_seconds is not None else DEFAULT_WINDOW_SECONDS
    
    # Flag para evitar doble conteo de métrica redis_unavailable
    redis_unavailable_counted = False
    
    # Intentar obtener cliente Redis
    redis_client: Optional[Any] = None
    try:
        redis_client = await get_async_redis_client()
    except Exception as e:
        _logger.warning(
            "touch_debounce_redis_unavailable: project_id=%s reason=%s error=%s fallback=allow_touch",
            str(project_id)[:8],
            reason,
            str(e),
        )
        _inc_metric_redis_unavailable(reason)
        redis_unavailable_counted = True
        # Redis no disponible → fail-open, ejecutar touch
    
    if redis_client is None:
        # Redis no configurado o no disponible → ejecutar touch directo
        _logger.debug(
            "touch_debounce_redis_not_available: project_id=%s reason=%s fallback=allow_touch",
            str(project_id)[:8],
            reason,
        )
        if not redis_unavailable_counted:
            _inc_metric_redis_unavailable(reason)
        
        # Ejecutar touch sin debounce
        try:
            touch_result = await touch_project_updated_at(db, project_id, reason=reason)
            _logger.info(
                "touch_project_debounced_allowed: project_id=%s reason=%s window_s=%d redis=unavailable result=%s",
                str(project_id)[:8],
                reason,
                effective_window,
                touch_result,
            )
            _inc_metric_allowed(reason)
            return touch_result
        except Exception as e:
            _logger.warning(
                "touch_project_debounced_error: project_id=%s reason=%s error=%s",
                str(project_id)[:8],
                reason,
                str(e),
            )
            return False
    
    # Intentar adquirir lock de debounce
    lock_acquired = await _try_acquire_debounce_lock(
        redis_client=redis_client,
        project_id=project_id,
        reason=reason,
        window_seconds=effective_window,
    )
    
    if not lock_acquired:
        # Ya hay touch reciente para este proyecto+reason → skip
        _logger.info(
            "touch_project_debounced_skipped: project_id=%s reason=%s window_s=%d",
            str(project_id)[:8],
            reason,
            effective_window,
        )
        _inc_metric_skipped(reason)
        return False
    
    # Lock adquirido → ejecutar touch real
    try:
        touch_result = await touch_project_updated_at(db, project_id, reason=reason)
        _logger.info(
            "touch_project_debounced_allowed: project_id=%s reason=%s window_s=%d result=%s",
            str(project_id)[:8],
            reason,
            effective_window,
            touch_result,
        )
        _inc_metric_allowed(reason)
        return touch_result
    except Exception as e:
        _logger.warning(
            "touch_project_debounced_error: project_id=%s reason=%s error=%s",
            str(project_id)[:8],
            reason,
            str(e),
        )
        return False


__all__ = [
    "touch_project_debounced",
    "DEBOUNCE_KEY_PREFIX",
    "DEFAULT_WINDOW_SECONDS",
    "_get_default_window_seconds",  # Exported for testing
]

# Fin del archivo backend/app/modules/projects/services/touch_debouncer.py
