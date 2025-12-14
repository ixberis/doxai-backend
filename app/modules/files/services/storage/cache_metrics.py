# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/cache_metrics.py

Sistema de métricas para monitorear el rendimiento del cache.
Proporciona estadísticas de hits, misses, evictions, y tamaños.

Autor: DoxAI
Fecha: 2025-11-05
"""

from dataclasses import dataclass, field
from typing import Dict
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheMetrics:
    """Métricas del cache."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    sets: int = 0
    deletes: int = 0
    total_bytes_cached: int = 0
    total_bytes_served: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def total_requests(self) -> int:
        """Total de solicitudes (hits + misses)."""
        return self.hits + self.misses
    
    @property
    def hit_rate(self) -> float:
        """Tasa de acierto (0.0 - 1.0)."""
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests
    
    @property
    def miss_rate(self) -> float:
        """Tasa de fallo (0.0 - 1.0)."""
        return 1.0 - self.hit_rate
    
    @property
    def uptime_seconds(self) -> float:
        """Tiempo de funcionamiento en segundos."""
        return time.time() - self.start_time
    
    @property
    def requests_per_second(self) -> float:
        """Solicitudes por segundo."""
        if self.uptime_seconds == 0:
            return 0.0
        return self.total_requests / self.uptime_seconds
    
    @property
    def avg_bytes_per_request(self) -> float:
        """Promedio de bytes por solicitud."""
        if self.total_requests == 0:
            return 0.0
        return self.total_bytes_served / self.total_requests
    
    def record_hit(self, size_bytes: int = 0) -> None:
        """Registra un cache hit."""
        self.hits += 1
        self.total_bytes_served += size_bytes
    
    def record_miss(self) -> None:
        """Registra un cache miss."""
        self.misses += 1
    
    def record_set(self, size_bytes: int) -> None:
        """Registra un set al cache."""
        self.sets += 1
        self.total_bytes_cached += size_bytes
    
    def record_eviction(self, size_bytes: int = 0) -> None:
        """Registra una evicción."""
        self.evictions += 1
        if size_bytes > 0:
            self.total_bytes_cached = max(0, self.total_bytes_cached - size_bytes)
    
    def record_expiration(self, size_bytes: int = 0) -> None:
        """Registra una expiración por TTL."""
        self.expirations += 1
        if size_bytes > 0:
            self.total_bytes_cached = max(0, self.total_bytes_cached - size_bytes)
    
    def record_delete(self, size_bytes: int = 0) -> None:
        """Registra un delete explícito."""
        self.deletes += 1
        if size_bytes > 0:
            self.total_bytes_cached = max(0, self.total_bytes_cached - size_bytes)
    
    def reset(self) -> None:
        """Reinicia todas las métricas."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0
        self.sets = 0
        self.deletes = 0
        self.total_bytes_cached = 0
        self.total_bytes_served = 0
        self.start_time = time.time()
    
    def to_dict(self) -> Dict[str, any]:
        """Convierte las métricas a diccionario."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "sets": self.sets,
            "deletes": self.deletes,
            "total_requests": self.total_requests,
            "hit_rate": self.hit_rate,
            "miss_rate": self.miss_rate,
            "total_bytes_cached": self.total_bytes_cached,
            "total_bytes_served": self.total_bytes_served,
            "uptime_seconds": self.uptime_seconds,
            "requests_per_second": self.requests_per_second,
            "avg_bytes_per_request": self.avg_bytes_per_request,
        }
    
    def log_summary(self, level: int = logging.INFO) -> None:
        """Registra un resumen de las métricas."""
        logger.log(
            level,
            f"📊 Cache Metrics Summary:\n"
            f"  Requests: {self.total_requests} ({self.requests_per_second:.2f}/s)\n"
            f"  Hit Rate: {self.hit_rate*100:.1f}% ({self.hits} hits, {self.misses} misses)\n"
            f"  Evictions: {self.evictions}, Expirations: {self.expirations}\n"
            f"  Cached: {self.total_bytes_cached:,} bytes\n"
            f"  Served: {self.total_bytes_served:,} bytes\n"
            f"  Uptime: {self.uptime_seconds:.1f}s"
        )
    
    def __str__(self) -> str:
        """Representación en string."""
        return (
            f"CacheMetrics(requests={self.total_requests}, "
            f"hit_rate={self.hit_rate*100:.1f}%, "
            f"cached={self.total_bytes_cached:,}b)"
        )


__all__ = ["CacheMetrics"]
