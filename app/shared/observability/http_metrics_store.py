# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/http_metrics_store.py

In-memory store para contadores HTTP con flush periódico a DB.
Patrón: contadores en memoria por proceso + flush cada N segundos.

MULTI-REPLICA: Este store es in-memory y best-effort.
Para conteos exactos en multi-replica, usar RedisHttpMetricsStore.

Autor: Sistema
Fecha: 2026-01-06
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Protocol, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # Solo para type-checkers (Pylance/MyPy). No se ejecuta en runtime.
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.shared.observability.redis_http_metrics_store import (  # pragma: no cover
        DisabledHttpMetricsStore,
        RedisHttpMetricsStore,
    )


# ---------------------------------------------------------------------------
# Type contracts
# ---------------------------------------------------------------------------

class HttpMetricsStoreBase(Protocol):
    """Contrato mínimo para stores de métricas HTTP (in-memory / redis / disabled)."""

    def set_session_factory(self, session_factory: Callable[[], "AsyncSession"]) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def increment(self, scope: str, status_code: int) -> None: ...
    async def flush(self) -> None: ...


# Singleton store instance
_http_metrics_store: Optional[HttpMetricsStoreBase] = None


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

class HttpMetricsStore(HttpMetricsStoreBase):
    """
    In-memory store para contadores HTTP.

    Thread-safe para FastAPI (single process async).
    Flush periódico a tabla http_request_metrics_daily.

    NOTA MULTI-REPLICA: Este store es in-memory y best-effort.
    En entornos multi-replica, cada instancia mantiene sus propios contadores.
    Los conteos serán aproximados (suma de todas las réplicas en flush).
    Para conteos exactos en multi-replica, usar RedisHttpMetricsStore.
    """

    # 4xx codes to EXCLUDE by default (auth-related expected errors)
    DEFAULT_4XX_EXCLUDED: frozenset[int] = frozenset({401, 403, 404})

    def __init__(
        self,
        flush_interval_seconds: int = 60,
        excluded_4xx_codes: Optional[frozenset[int]] = None,
    ):
        """
        Args:
            flush_interval_seconds: Intervalo de flush a DB (default 60s)
            excluded_4xx_codes: Set de códigos 4xx a excluir (default: {401, 403, 404})
        """
        self.flush_interval = int(flush_interval_seconds)
        self.excluded_4xx_codes = excluded_4xx_codes if excluded_4xx_codes is not None else self.DEFAULT_4XX_EXCLUDED
        self._counters: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(
            lambda: {"http_4xx_count": 0, "http_5xx_count": 0}
        )
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._db_session_factory: Optional[Callable[[], Any]] = None
        self._running = False

    def set_session_factory(self, session_factory: Callable[[], Any]) -> None:
        """Set the async session factory for DB operations."""
        self._db_session_factory = session_factory

    async def start(self) -> None:
        """Start the periodic flush task."""
        if not self._running:
            self._running = True
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info("HttpMetricsStore started with flush_interval=%ds", self.flush_interval)

    async def stop(self) -> None:
        """Stop the periodic flush task and perform final flush."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._flush_task), timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        # Final flush on shutdown (best-effort with timeout to avoid blocking)
        if not self._db_session_factory:
            return
        try:
            await asyncio.wait_for(self.flush(), timeout=2.0)
            logger.info("HttpMetricsStore: final flush completed on shutdown")
        except asyncio.TimeoutError:
            logger.warning("HttpMetricsStore: final flush timed out (2s), continuing shutdown")
        except Exception as e:
            logger.warning("HttpMetricsStore: final flush failed: %s", e)

    async def increment(self, scope: str, status_code: int) -> None:
        """
        Increment counter for a status code.

        - 5xx: Always counted
        - 4xx: Counted UNLESS in excluded_4xx_codes (default: {401, 403, 404})

        Args:
            scope: Scope identifier (e.g., "auth", "api")
            status_code: HTTP status code
        """
        today = date.today().isoformat()
        key = (today, scope)

        async with self._lock:
            if 500 <= status_code < 600:
                self._counters[key]["http_5xx_count"] += 1
            elif 400 <= status_code < 500:
                if status_code not in self.excluded_4xx_codes:
                    self._counters[key]["http_4xx_count"] += 1

    async def _flush_loop(self) -> None:
        """Background task that flushes to DB periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("HttpMetricsStore flush error: %s", e)

    async def flush(self) -> None:
        """Flush current counters to database."""
        if not self._db_session_factory:
            logger.warning("HttpMetricsStore: no session factory, skipping flush")
            return

        async with self._lock:
            if not self._counters:
                return

            # Snapshot and reset
            to_flush = dict(self._counters)
            self._counters.clear()

        try:
            async with self._db_session_factory() as db:
                for (day, scope), counts in to_flush.items():
                    if counts["http_4xx_count"] == 0 and counts["http_5xx_count"] == 0:
                        continue

                    q = text(
                        """
                        INSERT INTO public.http_request_metrics_daily
                            (date, scope, http_4xx_count, http_5xx_count, updated_at)
                        VALUES (:date, :scope, :http_4xx, :http_5xx, :now)
                        ON CONFLICT (date, scope) DO UPDATE SET
                            http_4xx_count = http_request_metrics_daily.http_4xx_count + :http_4xx,
                            http_5xx_count = http_request_metrics_daily.http_5xx_count + :http_5xx,
                            updated_at = :now
                        """
                    )
                    await db.execute(
                        q,
                        {
                            "date": day,
                            "scope": scope,
                            "http_4xx": counts["http_4xx_count"],
                            "http_5xx": counts["http_5xx_count"],
                            "now": datetime.now(timezone.utc),
                        },
                    )

                await db.commit()
                logger.debug("HttpMetricsStore flushed %d entries", len(to_flush))
        except Exception as e:
            logger.error("HttpMetricsStore DB flush failed: %s", e)
            # Re-add counters on failure (best effort)
            async with self._lock:
                for key, counts in to_flush.items():
                    self._counters[key]["http_4xx_count"] += counts["http_4xx_count"]
                    self._counters[key]["http_5xx_count"] += counts["http_5xx_count"]

    def get_counters_snapshot(self) -> Dict[Tuple[str, str], Dict[str, int]]:
        """Get a snapshot of current counters (for testing)."""
        return dict(self._counters)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_http_metrics_store(
    use_redis: bool = True,
    flush_interval_seconds: int = 60,
    excluded_4xx_codes: Optional[frozenset[int]] = None,
) -> HttpMetricsStoreBase:
    """
    Factory function to get the appropriate HTTP metrics store.

    Selection logic:
    1. If HTTP_METRICS_ENABLED=false → DisabledHttpMetricsStore (no-op)
    2. If redis_url present and use_redis=True → RedisHttpMetricsStore (exact multi-replica)
    3. Otherwise → HttpMetricsStore (in-memory, best-effort)

    Settings are read from snake_case attributes first, then env vars as fallback.
    """
    global _http_metrics_store

    if _http_metrics_store is not None:
        return _http_metrics_store

    # Defaults
    metrics_enabled: bool = True
    single_instance_warning: bool = True
    redis_url: Optional[str] = None

    # Read settings module if available
    try:
        from app.shared.config import settings

        metrics_enabled = bool(
            getattr(settings, "http_metrics_enabled", getattr(settings, "HTTP_METRICS_ENABLED", True))
        )
        single_instance_warning = bool(
            getattr(
                settings,
                "http_metrics_single_instance_warning",
                getattr(settings, "HTTP_METRICS_SINGLE_INSTANCE_WARNING", True),
            )
        )
        redis_url = getattr(settings, "redis_url", getattr(settings, "REDIS_URL", None))
    except Exception:
        pass

    # Fallback to env vars if not set from settings
    if redis_url is None:
        redis_url = os.getenv("REDIS_URL")

    # HTTP_METRICS_ENABLED logic:
    # - In dev/test: disabled by default
    # - In prod/staging: enabled by default
    # - Explicit HTTP_METRICS_ENABLED=true/false always wins
    env_val = os.getenv("HTTP_METRICS_ENABLED", "").strip().lower()
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()

    if env_val in ("true", "1", "yes", "y"):
        metrics_enabled = True
    elif env_val in ("false", "0", "no", "n"):
        metrics_enabled = False
    elif environment in ("production", "staging"):
        metrics_enabled = True
    else:
        metrics_enabled = False

    # Optional: warning toggle
    env_warn = os.getenv("HTTP_METRICS_SINGLE_INSTANCE_WARNING", "").strip().lower()
    if env_warn in ("false", "0", "no", "n"):
        single_instance_warning = False

    # Option 1: Disabled
    if not metrics_enabled:
        logger.info("HttpMetricsStore: http_metrics_enabled=false, using DisabledHttpMetricsStore")
        from app.shared.observability.redis_http_metrics_store import DisabledHttpMetricsStore

        _http_metrics_store = DisabledHttpMetricsStore(
            excluded_4xx_codes=excluded_4xx_codes,
        )
        return _http_metrics_store

    # Option 2: Redis available
    if redis_url and use_redis:
        try:
            import redis.asyncio as aioredis
            from app.shared.observability.redis_http_metrics_store import RedisHttpMetricsStore

            redis_client = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

            _http_metrics_store = RedisHttpMetricsStore(
                redis_client=redis_client,
                flush_interval_seconds=flush_interval_seconds,
                excluded_4xx_codes=excluded_4xx_codes,
            )
            logger.info(
                "HttpMetricsStore: redis_url detected, using RedisHttpMetricsStore "
                "(exact multi-replica counters)"
            )
            return _http_metrics_store
        except ImportError:
            logger.warning("HttpMetricsStore: redis.asyncio not available, falling back to in-memory store")
        except Exception as e:
            logger.warning("HttpMetricsStore: failed to init Redis store (%s), falling back to in-memory", e)

    # Option 3: In-memory fallback
    if single_instance_warning and not redis_url:
        logger.warning(
            "HttpMetricsStore: No redis_url configured. Using in-memory store (best-effort). "
            "HTTP metrics may be inaccurate in multi-replica deployments. "
            "Set HTTP_METRICS_SINGLE_INSTANCE_WARNING=false to suppress this warning."
        )

    _http_metrics_store = HttpMetricsStore(
        flush_interval_seconds=flush_interval_seconds,
        excluded_4xx_codes=excluded_4xx_codes,
    )
    return _http_metrics_store


def reset_http_metrics_store() -> None:
    """Reset the global store instance (for testing)."""
    global _http_metrics_store
    _http_metrics_store = None

# Fin del archivo backend\app\shared\observability\http_metrics_store.py
