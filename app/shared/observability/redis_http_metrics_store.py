# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/redis_http_metrics_store.py

Redis-based store para contadores HTTP con flush atómico a DB.
Usa redis.asyncio con INCRBY atómico para conteos exactos en entornos multi-replica.

Keys format:
    http:metrics:{scope}:{YYYY-MM-DD}:4xx
    http:metrics:{scope}:{YYYY-MM-DD}:5xx

Estrategia de flush (sin pérdida, atómico):
    1. GETSET(key, "0") - lee y resetea atómicamente
    2. UPSERT delta a Postgres + COMMIT
    3. Si DB falla: INCRBY(key, delta) para rollback

Autor: Sistema
Fecha: 2026-01-06
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Key pattern for Redis
KEY_PREFIX = "http:metrics"
KEY_TTL_SECONDS = 172800  # 48 hours

# Default scopes to always flush (survives restarts)
DEFAULT_CONFIGURED_SCOPES: frozenset = frozenset({"auth"})


class RedisHttpMetricsStore:
    """
    Redis-based store para contadores HTTP.
    
    Usa redis.asyncio con INCRBY atómico para conteos exactos en multi-replica.
    Flush periódico a tabla http_request_metrics_daily.
    
    Keys:
        http:metrics:{scope}:{YYYY-MM-DD}:4xx
        http:metrics:{scope}:{YYYY-MM-DD}:5xx
    """
    
    # 4xx codes to EXCLUDE by default (auth-related expected errors)
    DEFAULT_4XX_EXCLUDED: frozenset = frozenset({401, 403, 404})
    
    def __init__(
        self,
        redis_client,
        flush_interval_seconds: int = 60,
        excluded_4xx_codes: Optional[frozenset] = None,
        key_ttl_seconds: int = KEY_TTL_SECONDS,
        configured_scopes: Optional[frozenset] = None,
    ):
        """
        Args:
            redis_client: Async Redis client (redis.asyncio)
            flush_interval_seconds: Intervalo de flush a DB (default 60s)
            excluded_4xx_codes: Set de códigos 4xx a excluir (default: {401, 403, 404})
            key_ttl_seconds: TTL for Redis keys (default: 48h)
            configured_scopes: Scopes to always flush (default: {"auth"})
        """
        self._redis = redis_client
        self.flush_interval = flush_interval_seconds
        self.excluded_4xx_codes = excluded_4xx_codes if excluded_4xx_codes is not None else self.DEFAULT_4XX_EXCLUDED
        self.key_ttl = key_ttl_seconds
        self._configured_scopes = configured_scopes if configured_scopes is not None else DEFAULT_CONFIGURED_SCOPES
        self._dynamic_scopes: Set[str] = set()  # Additional scopes discovered at runtime
        self._flush_task: Optional[asyncio.Task] = None
        self._db_session_factory = None
        self._running = False
        self._flush_lock = asyncio.Lock()  # Prevent concurrent flushes
    
    def set_session_factory(self, session_factory):
        """Set the async session factory for DB operations."""
        self._db_session_factory = session_factory
    
    def add_scope(self, scope: str):
        """Add a dynamic scope to track (in addition to configured scopes)."""
        self._dynamic_scopes.add(scope)
    
    def _get_all_scopes(self) -> Set[str]:
        """Get all scopes to flush (configured + dynamic)."""
        return set(self._configured_scopes) | self._dynamic_scopes
    
    async def start(self):
        """Start the periodic flush task."""
        if not self._running:
            self._running = True
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info(
                "RedisHttpMetricsStore started with flush_interval=%ds, key_ttl=%ds, scopes=%s",
                self.flush_interval,
                self.key_ttl,
                list(self._get_all_scopes()),
            )
    
    async def stop(self):
        """Stop the periodic flush task and perform final flush."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                # Wait briefly for task to acknowledge cancellation
                await asyncio.wait_for(asyncio.shield(self._flush_task), timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        # Final flush on shutdown (best-effort with timeout to avoid blocking)
        if not self._db_session_factory:
            return
        try:
            await asyncio.wait_for(self.flush(), timeout=2.0)
            logger.info("RedisHttpMetricsStore: final flush completed on shutdown")
        except asyncio.TimeoutError:
            logger.warning("RedisHttpMetricsStore: final flush timed out (2s), continuing shutdown")
        except Exception as e:
            logger.warning("RedisHttpMetricsStore: final flush failed: %s", e)
    
    def _make_key(self, scope: str, day: str, error_type: str) -> str:
        """Generate Redis key for a counter."""
        return f"{KEY_PREFIX}:{scope}:{day}:{error_type}"
    
    async def increment(self, scope: str, status_code: int):
        """
        Increment counter for a status code using Redis INCRBY (atomic).
        
        - 5xx: Always counted
        - 4xx: Counted UNLESS in excluded_4xx_codes (default: {401, 403, 404})
        
        Args:
            scope: Scope identifier (e.g., "auth", "api")
            status_code: HTTP status code
        """
        today = date.today().isoformat()
        self._dynamic_scopes.add(scope)
        
        key: Optional[str] = None
        
        if 500 <= status_code < 600:
            # Always count 5xx
            key = self._make_key(scope, today, "5xx")
        elif 400 <= status_code < 500:
            # Count 4xx unless excluded
            if status_code not in self.excluded_4xx_codes:
                key = self._make_key(scope, today, "4xx")
        
        if key:
            try:
                # Use async Redis client - INCRBY is atomic, safe for multi-replica
                await self._redis.incrby(key, 1)
                # Set TTL if key is new (or refresh it)
                await self._redis.expire(key, self.key_ttl)
            except Exception as e:
                logger.warning("RedisHttpMetricsStore increment failed: %s", e)
    
    async def _flush_loop(self):
        """Background task that flushes to DB periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("RedisHttpMetricsStore flush error: %s", e)
    
    def _get_keys_to_flush(self) -> List[str]:
        """
        Get list of known keys to flush (today and yesterday only).
        Uses configured + dynamic scopes. No SCAN.
        """
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        keys = []
        for day in [today.isoformat(), yesterday.isoformat()]:
            for scope in self._get_all_scopes():
                for error_type in ["4xx", "5xx"]:
                    keys.append(self._make_key(scope, day, error_type))
        
        return keys
    
    async def _atomic_get_and_reset(self, key: str) -> Optional[int]:
        """
        Atomically get current value and reset to 0.
        
        Uses SET with GET option (Redis 6.2+) or GETSET fallback.
        - TypeError/ResponseError: fallback to GETSET
        - ConnectionError/TimeoutError: log warning, return None (no fallback)
        
        Returns the delta value, or None if key didn't exist or on network error.
        """
        # Import redis exceptions lazily to avoid hard dependency at module level
        try:
            from redis.exceptions import ResponseError, ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
        except ImportError:
            # If redis.exceptions not available, define as never-matching types
            ResponseError = type(None)
            RedisConnectionError = type(None)
            RedisTimeoutError = type(None)
        
        try:
            # Try SET with GET option (Redis 6.2+): SET key 0 GET
            # This atomically sets to 0 and returns old value
            old_value = await self._redis.set(key, "0", get=True)
            
            if old_value is None:
                return None
            
            delta = int(old_value)
            if delta == 0:
                return None
            
            # Refresh TTL after reset
            await self._redis.expire(key, self.key_ttl)
            return delta
            
        except (TypeError, ResponseError) as e:
            # TypeError: older redis-py without GET option
            # ResponseError: server doesn't support SET ... GET
            # Fallback to GETSET (deprecated but widely supported)
            # Rate-limited warning: 1/5min to avoid spam but maintain visibility
            from app.shared.utils.log_throttle import log_once_every
            log_once_every(
                "redis_metrics_getset_fallback", 300,
                logger, logging.WARNING,
                "RedisHttpMetricsStore: falling back to GETSET (older Redis): %s", str(e)
            )
            
            try:
                old_value = await self._redis.getset(key, "0")
                if old_value is None:
                    return None
                delta = int(old_value)
                if delta == 0:
                    return None
                await self._redis.expire(key, self.key_ttl)
                return delta
            except Exception as fallback_e:
                logger.warning("RedisHttpMetricsStore _atomic_get_and_reset fallback failed: %s", fallback_e)
                return None
        
        except (RedisConnectionError, RedisTimeoutError, ConnectionError, TimeoutError, OSError) as e:
            # Network errors: log warning, don't attempt fallback (same issue would occur)
            logger.warning("RedisHttpMetricsStore: network error on %s, skipping: %s", key, e)
            return None
        
        except Exception as e:
            # Unexpected error: log and return None
            logger.warning("RedisHttpMetricsStore _atomic_get_and_reset failed for %s: %s", key, e)
            return None
    
    async def _rollback_delta(self, key: str, delta: int):
        """Rollback a delta by adding it back to Redis (best-effort)."""
        try:
            await self._redis.incrby(key, delta)
            await self._redis.expire(key, self.key_ttl)
            # Note: Rollback logged at INFO level in flush() summary, not per-key
        except Exception as e:
            logger.error(
                "RedisHttpMetricsStore: CRITICAL - failed to rollback delta=%d to key=%s: %s. "
                "Data may be lost.",
                delta, key, e
            )
    
    async def flush(self):
        """
        Flush Redis counters to Postgres using atomic reset.
        
        Strategy (no data loss):
            1. For each key: GETSET(key, "0") - atomically read and reset
            2. Aggregate deltas by (day, scope)
            3. UPSERT to Postgres + COMMIT
            4. If DB fails: INCRBY(key, delta) to rollback each key
        
        Any increments that happen AFTER GETSET are preserved in Redis.
        Uses lock to prevent concurrent flushes.
        """
        if not self._db_session_factory:
            logger.warning("RedisHttpMetricsStore: no session factory, skipping flush")
            return
        
        # Acquire lock to prevent concurrent flushes (e.g., periodic + shutdown)
        if self._flush_lock.locked():
            # Rate-limited log: flush already in progress (1/min)
            from app.shared.utils.log_throttle import log_once_every
            log_once_every(
                "redis_metrics_flush_in_progress", 60,
                logger, logging.DEBUG,
                "RedisHttpMetricsStore: flush already in progress, skipping"
            )
            return
        
        async with self._flush_lock:
        
            # Step 1: Atomically read and reset all keys
            keys_to_flush = self._get_keys_to_flush()
            deltas: Dict[str, int] = {}  # key -> delta (for rollback)
            to_flush: Dict[Tuple[str, str], Dict[str, int]] = {}  # (day, scope) -> counts
            
            for key in keys_to_flush:
                delta = await self._atomic_get_and_reset(key)
                if delta is None or delta == 0:
                    continue
                
                deltas[key] = delta
                
                # Parse key: http:metrics:{scope}:{YYYY-MM-DD}:{4xx|5xx}
                parts = key.split(":")
                if len(parts) != 5:
                    continue
                
                _, _, scope, day, error_type = parts
                agg_key = (day, scope)
                
                if agg_key not in to_flush:
                    to_flush[agg_key] = {"http_4xx_count": 0, "http_5xx_count": 0}
                
                if error_type == "4xx":
                    to_flush[agg_key]["http_4xx_count"] += delta
                else:
                    to_flush[agg_key]["http_5xx_count"] += delta
            
            if not to_flush:
                # Silently skip - no need to log "nothing to flush" on every interval
                return
            
            # Step 2: Write to Postgres
            try:
                async with self._db_session_factory() as db:
                    for (day, scope), counts in to_flush.items():
                        if counts["http_4xx_count"] == 0 and counts["http_5xx_count"] == 0:
                            continue
                        
                        # Upsert: increment existing or insert new
                        q = text("""
                            INSERT INTO public.http_request_metrics_daily 
                                (date, scope, http_4xx_count, http_5xx_count, updated_at)
                            VALUES (:date, :scope, :http_4xx, :http_5xx, :now)
                            ON CONFLICT (date, scope) DO UPDATE SET
                                http_4xx_count = http_request_metrics_daily.http_4xx_count + :http_4xx,
                                http_5xx_count = http_request_metrics_daily.http_5xx_count + :http_5xx,
                                updated_at = :now
                        """)
                        await db.execute(q, {
                            "date": day,
                            "scope": scope,
                            "http_4xx": counts["http_4xx_count"],
                            "http_5xx": counts["http_5xx_count"],
                            "now": datetime.now(timezone.utc),
                        })
                    
                    await db.commit()
                    logger.info(
                        "RedisHttpMetricsStore flushed %d entries to Postgres",
                        len(to_flush),
                    )
            except Exception as e:
                logger.error("RedisHttpMetricsStore DB flush failed: %s - rolling back to Redis", e)
                
                # Step 3: Rollback - add deltas back to Redis
                for key, delta in deltas.items():
                    await self._rollback_delta(key, delta)
                
                logger.info("RedisHttpMetricsStore: rollback complete, %d keys restored", len(deltas))
    
    async def get_counters_snapshot(self) -> Dict[Tuple[str, str], Dict[str, int]]:
        """
        Get a snapshot of current Redis counters (for testing).
        
        Returns dict similar to in-memory store format.
        """
        result: Dict[Tuple[str, str], Dict[str, int]] = {}
        
        try:
            for key in self._get_keys_to_flush():
                value = await self._redis.get(key)
                if value is None:
                    continue
                
                count = int(value)
                if count == 0:
                    continue
                
                parts = key.split(":")
                if len(parts) != 5:
                    continue
                
                _, _, scope, day, error_type = parts
                agg_key = (day, scope)
                
                if agg_key not in result:
                    result[agg_key] = {"http_4xx_count": 0, "http_5xx_count": 0}
                
                if error_type == "4xx":
                    result[agg_key]["http_4xx_count"] += count
                else:
                    result[agg_key]["http_5xx_count"] += count
                    
        except Exception as e:
            logger.warning("RedisHttpMetricsStore get_counters_snapshot failed: %s", e)
        
        return result


class DisabledHttpMetricsStore:
    """
    No-op store when HTTP metrics are disabled.
    
    All methods are no-ops to avoid overhead.
    """
    
    DEFAULT_4XX_EXCLUDED: frozenset = frozenset({401, 403, 404})
    
    def __init__(self, **kwargs):
        self.excluded_4xx_codes = kwargs.get("excluded_4xx_codes", self.DEFAULT_4XX_EXCLUDED)
        self._running = False
    
    def set_session_factory(self, session_factory):
        pass
    
    async def start(self):
        # Silently skip - metrics disabled, no need to log
    
    async def stop(self):
        pass
    
    async def increment(self, scope: str, status_code: int):
        pass
    
    async def flush(self):
        pass
    
    async def get_counters_snapshot(self) -> Dict[Tuple[str, str], Dict[str, int]]:
        return {}
