# -*- coding: utf-8 -*-
"""
backend/app/shared/observability/db_metrics_collector.py

DB-to-Prometheus Exporter: Gauges refrescados periódicamente desde DB.

Métricas expuestas:
- doxai_ghost_files_count: Archivos fantasma pendientes
- doxai_jobs_failed_24h: Jobs fallidos en últimas 24h
- doxai_jobs_critical_last_status{job_id}: Estado del último job crítico
- doxai_storage_delta_total: Inconsistencia storage vs DB

Design:
- Refresh cada 60s (configurable)
- Cache en memoria con último valor conocido
- Degradación graceful si DB falla (usa último valor + incrementa error counter)
- /metrics responde rápido (no bloquea en DB)

Autor: DoxAI
Fecha: 2026-01-23
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.metrics_helpers import get_or_create_gauge, get_or_create_counter

_logger = logging.getLogger("observability.db_metrics")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

REFRESH_INTERVAL_SECONDS = 60
STALE_THRESHOLD_SECONDS = 120  # Consider data stale after 2x refresh interval

# Critical jobs to monitor (low cardinality - only these get individual gauges)
CRITICAL_JOBS = [
    "files_reconcile_storage_ghosts",
    "admin_cleanup_ghost_files",
    "admin_cleanup_storage_snapshots",
]

# ═══════════════════════════════════════════════════════════════════════════════
# METRIC NAMES
# ═══════════════════════════════════════════════════════════════════════════════

GHOST_FILES_COUNT_NAME = "doxai_ghost_files_count"
JOBS_FAILED_24H_NAME = "doxai_jobs_failed_24h"
JOBS_CRITICAL_STATUS_NAME = "doxai_jobs_critical_last_status"
STORAGE_DELTA_NAME = "doxai_storage_delta_total"
DB_METRICS_ERRORS_NAME = "doxai_db_metrics_errors_total"
DB_METRICS_LAST_REFRESH_NAME = "doxai_db_metrics_last_refresh_timestamp"

# ═══════════════════════════════════════════════════════════════════════════════
# SQL QUERIES
# ═══════════════════════════════════════════════════════════════════════════════

SQL_GHOST_FILES_COUNT = text("""
    SELECT COUNT(*) AS cnt
    FROM public.input_files
    WHERE input_file_is_active = true
      AND storage_exists = false
""")

SQL_JOBS_FAILED_24H = text("""
    SELECT COUNT(*) AS cnt
    FROM kpis.job_executions
    WHERE status = 'failed'
      AND started_at > NOW() - INTERVAL '24 hours'
      AND module IN ('files', 'storage', 'projects')
""")

SQL_JOB_CRITICAL_LAST_STATUS = text("""
    SELECT 
        job_id,
        status,
        started_at
    FROM kpis.job_executions
    WHERE job_id = ANY(:job_ids)
    ORDER BY started_at DESC
""")

# SSOT: public.v_kpis_storage_snapshot con campos canónicos
SQL_STORAGE_DELTA = text("""
    SELECT 
        COALESCE(input_delta_storage_vs_db, 0) AS input_delta,
        COALESCE(product_delta_storage_vs_db, 0) AS product_delta
    FROM public.v_kpis_storage_snapshot
    LIMIT 1
""")


# ═══════════════════════════════════════════════════════════════════════════════
# COLLECTOR CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class DBMetricsCollector:
    """
    Singleton collector that refreshes DB metrics periodically.
    
    Usage:
        collector = DBMetricsCollector.get_instance()
        await collector.refresh(db_session)  # Called periodically
    """
    
    _instance: Optional["DBMetricsCollector"] = None
    
    def __init__(self):
        self._initialized = False
        self._last_refresh: Optional[float] = None
        self._cached_values: Dict[str, Any] = {}
        
        # Gauges
        self._ghost_files_gauge: Optional[Any] = None
        self._jobs_failed_gauge: Optional[Any] = None
        self._jobs_critical_gauge: Optional[Any] = None
        self._storage_delta_gauge: Optional[Any] = None
        self._last_refresh_gauge: Optional[Any] = None
        
        # Error counter
        self._errors_counter: Optional[Any] = None
    
    @classmethod
    def get_instance(cls) -> "DBMetricsCollector":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _ensure_metrics(self) -> bool:
        """
        Initialize Prometheus metrics (lazy).
        
        Gauges sin labels se inicializan con valor 0 para que aparezcan.
        Gauges con labels (jobs críticos) se inicializan porque tienen cardinalidad fija.
        Counters con labels aparecen cuando hay actividad real.
        """
        if self._initialized:
            return True
        
        try:
            self._ghost_files_gauge = get_or_create_gauge(
                GHOST_FILES_COUNT_NAME,
                "Number of ghost files (DB records without storage object)",
            )
            self._jobs_failed_gauge = get_or_create_gauge(
                JOBS_FAILED_24H_NAME,
                "Number of failed jobs in last 24 hours",
            )
            self._jobs_critical_gauge = get_or_create_gauge(
                JOBS_CRITICAL_STATUS_NAME,
                "Last status of critical jobs (1=success, 0=failed, -1=never_ran)",
                labelnames=("job_id",),
            )
            self._storage_delta_gauge = get_or_create_gauge(
                STORAGE_DELTA_NAME,
                "Absolute sum of storage vs DB deltas (input + product)",
            )
            self._last_refresh_gauge = get_or_create_gauge(
                DB_METRICS_LAST_REFRESH_NAME,
                "Unix epoch seconds of last successful DB metrics refresh (time.time())",
            )
            self._errors_counter = get_or_create_counter(
                DB_METRICS_ERRORS_NAME,
                "Total errors during DB metrics refresh",
                labelnames=("metric",),
            )
            
            # Gauges sin labels: inicializar con 0 para que aparezcan en /metrics
            self._ghost_files_gauge.set(0)
            self._jobs_failed_gauge.set(0)
            self._storage_delta_gauge.set(0)
            self._last_refresh_gauge.set(0)
            
            # Gauge con labels: solo jobs críticos (cardinalidad fija = 3)
            for job_id in CRITICAL_JOBS:
                self._jobs_critical_gauge.labels(job_id=job_id).set(-1)
            
            self._initialized = True
            _logger.info("db_metrics_collector_initialized")
            return True
        except Exception as e:
            _logger.warning(f"db_metrics_init_error: {e}")
            return False
    
    def should_refresh(self) -> bool:
        """Check if refresh is needed based on interval."""
        if self._last_refresh is None:
            return True
        elapsed = time.time() - self._last_refresh
        return elapsed >= REFRESH_INTERVAL_SECONDS
    
    def is_stale(self) -> bool:
        """Check if cached data is stale (beyond 2x refresh interval)."""
        if self._last_refresh is None:
            return True
        elapsed = time.time() - self._last_refresh
        return elapsed >= STALE_THRESHOLD_SECONDS
    
    async def refresh(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Refresh all DB metrics.
        
        Returns dict with all metric values (for testing/debugging).
        On error, uses cached values and increments error counter.
        """
        if not self._ensure_metrics():
            return {"error": "metrics_not_initialized"}
        
        results: Dict[str, Any] = {}
        
        # 1. Ghost files count
        try:
            res = await db.execute(SQL_GHOST_FILES_COUNT)
            count = res.scalar() or 0
            self._ghost_files_gauge.set(count)
            results["ghost_files_count"] = count
            self._cached_values["ghost_files"] = count
        except Exception as e:
            _logger.warning(f"db_metrics_refresh_error metric=ghost_files: {e}")
            self._errors_counter.labels(metric="ghost_files").inc()
            results["ghost_files_count"] = self._cached_values.get("ghost_files", -1)
        
        # 2. Jobs failed 24h
        try:
            res = await db.execute(SQL_JOBS_FAILED_24H)
            count = res.scalar() or 0
            self._jobs_failed_gauge.set(count)
            results["jobs_failed_24h"] = count
            self._cached_values["jobs_failed"] = count
        except Exception as e:
            _logger.warning(f"db_metrics_refresh_error metric=jobs_failed: {e}")
            self._errors_counter.labels(metric="jobs_failed").inc()
            results["jobs_failed_24h"] = self._cached_values.get("jobs_failed", -1)
        
        # 3. Critical jobs last status
        try:
            res = await db.execute(
                SQL_JOB_CRITICAL_LAST_STATUS,
                {"job_ids": CRITICAL_JOBS}
            )
            rows = res.fetchall()
            
            # Build map of latest status per job
            job_status_map: Dict[str, int] = {job: -1 for job in CRITICAL_JOBS}  # -1 = never ran
            seen_jobs = set()
            
            for row in rows:
                job_id = row.job_id
                if job_id in seen_jobs:
                    continue  # Already got latest for this job
                seen_jobs.add(job_id)
                
                status = row.status
                if status == "success":
                    job_status_map[job_id] = 1
                elif status == "failed":
                    job_status_map[job_id] = 0
                # running = keep as -1 (pending)
            
            for job_id, status_val in job_status_map.items():
                self._jobs_critical_gauge.labels(job_id=job_id).set(status_val)
            
            results["jobs_critical_status"] = job_status_map
            self._cached_values["jobs_critical"] = job_status_map
        except Exception as e:
            _logger.warning(f"db_metrics_refresh_error metric=jobs_critical: {e}")
            self._errors_counter.labels(metric="jobs_critical").inc()
            results["jobs_critical_status"] = self._cached_values.get("jobs_critical", {})
        
        # 4. Storage delta
        try:
            res = await db.execute(SQL_STORAGE_DELTA)
            row = res.fetchone()
            
            if row:
                input_delta = abs(row.input_delta or 0)
                product_delta = abs(row.product_delta or 0)
                total_delta = input_delta + product_delta
            else:
                total_delta = 0
            
            self._storage_delta_gauge.set(total_delta)
            results["storage_delta_total"] = total_delta
            self._cached_values["storage_delta"] = total_delta
        except Exception as e:
            _logger.warning(f"db_metrics_refresh_error metric=storage_delta: {e}")
            self._errors_counter.labels(metric="storage_delta").inc()
            results["storage_delta_total"] = self._cached_values.get("storage_delta", -1)
        
        # Update last refresh timestamp (epoch seconds)
        ts = int(time.time())
        self._last_refresh = float(ts)
        self._last_refresh_gauge.set(ts)
        results["last_refresh_timestamp"] = ts
        
        _logger.info(
            "db_metrics_refreshed ghost=%d jobs_failed=%d storage_delta=%d",
            results.get("ghost_files_count", -1),
            results.get("jobs_failed_24h", -1),
            results.get("storage_delta_total", -1),
        )
        
        return results
    
    def get_cached_values(self) -> Dict[str, Any]:
        """Get current cached values (for debugging)."""
        return {
            "ghost_files": self._cached_values.get("ghost_files"),
            "jobs_failed": self._cached_values.get("jobs_failed"),
            "jobs_critical": self._cached_values.get("jobs_critical"),
            "storage_delta": self._cached_values.get("storage_delta"),
            "last_refresh_timestamp": int(self._last_refresh) if self._last_refresh else 0,
            "is_stale": self.is_stale(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL API
# ═══════════════════════════════════════════════════════════════════════════════

def get_db_metrics_collector() -> DBMetricsCollector:
    """Get the singleton DB metrics collector."""
    return DBMetricsCollector.get_instance()


async def refresh_db_metrics_if_needed(db: AsyncSession) -> Optional[Dict[str, Any]]:
    """
    Refresh DB metrics if interval has elapsed.
    
    Safe to call frequently - only refreshes when needed.
    Returns refresh results if refreshed, None if skipped.
    """
    collector = get_db_metrics_collector()
    
    if not collector.should_refresh():
        return None
    
    return await collector.refresh(db)


__all__ = [
    "DBMetricsCollector",
    "get_db_metrics_collector",
    "refresh_db_metrics_if_needed",
    "GHOST_FILES_COUNT_NAME",
    "JOBS_FAILED_24H_NAME",
    "JOBS_CRITICAL_STATUS_NAME",
    "STORAGE_DELTA_NAME",
    "CRITICAL_JOBS",
]
