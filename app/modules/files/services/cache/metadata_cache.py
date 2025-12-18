# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/cache/metadata_cache.py

Sistema de caché en memoria para metadatos con TTL y LRU eviction.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MetadataCache:
    """Caché thread-safe con TTL y LRU eviction."""

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 3600,
        enable_stats: bool = True,
    ):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.enable_stats = enable_stats
        
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.RLock()
        
        # Estadísticas
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0

    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del caché."""
        with self._lock:
            if key not in self._cache:
                if self.enable_stats:
                    self._misses += 1
                return None

            value, expiry = self._cache[key]
            
            # Verificar expiración (None = nunca expira)
            if expiry is not None and expiry < time.time():
                del self._cache[key]
                if self.enable_stats:
                    self._misses += 1
                return None

            # Mover al final (LRU)
            self._cache.move_to_end(key)
            
            if self.enable_stats:
                self._hits += 1
            
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Almacena un valor en el caché."""
        with self._lock:
            ttl = ttl if ttl is not None else self.default_ttl
            expiry = time.time() + ttl

            # Si existe, actualizar
            if key in self._cache:
                self._cache[key] = (value, expiry)
                self._cache.move_to_end(key)
                return

            # Verificar límite de tamaño
            if len(self._cache) >= self.max_size:
                # Evict LRU (primero del OrderedDict)
                self._cache.popitem(last=False)
                if self.enable_stats:
                    self._evictions += 1

            self._cache[key] = (value, expiry)

    def invalidate(self, key: str) -> bool:
        """Invalida una entrada específica."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if self.enable_stats:
                    self._invalidations += 1
                return True
            return False

    def invalidate_pattern(self, prefix: str) -> int:
        """Invalida todas las entradas con un prefijo."""
        with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            count = len(keys_to_delete)
            
            for key in keys_to_delete:
                del self._cache[key]
            
            if self.enable_stats and count > 0:
                self._invalidations += count
            
            return count

    def clear(self) -> None:
        """Limpia todo el caché."""
        with self._lock:
            self._cache.clear()

    def cleanup(self) -> int:
        """
        Elimina entradas expiradas del caché.
        
        Recorre todas las entradas y elimina aquellas cuyo TTL ha expirado.
        Esta operación es thread-safe y no afecta entradas vigentes.
        Maneja casos donde expiry es None (entradas sin TTL) conservándolas.
        Loguea advertencia agregada si detecta entradas con formato inesperado.
        
        Returns:
            Número de entradas eliminadas.
        """
        with self._lock:
            now = time.time()
            expired_keys = []
            malformed_count = 0
            malformed_samples: list[str] = []  # Máx 3 ejemplos
            
            for key, entry in self._cache.items():
                # Manejar formato de tupla (value, expiry)
                if not isinstance(entry, tuple) or len(entry) != 2:
                    malformed_count += 1
                    if len(malformed_samples) < 3:
                        malformed_samples.append(f"{key}:{type(entry).__name__}")
                    continue  # Formato inesperado, conservar
                
                _, expiry = entry
                
                # Si expiry es None, la entrada no expira
                if expiry is None:
                    continue
                
                if expiry < now:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
            
            # Log agregado de entradas malformadas (rate-limited: 1x por cleanup)
            if malformed_count > 0:
                logger.warning(
                    "MetadataCache.cleanup detected %d malformed entries (samples: %s). "
                    "Expected format: (value, expiry). Entries preserved but may indicate corruption.",
                    malformed_count,
                    ", ".join(malformed_samples),
                )
            
            return len(expired_keys)

    def get_stats(self) -> dict:
        """Retorna estadísticas del caché."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "invalidations": self._invalidations,
                "hit_rate_percent": hit_rate,
                "total_requests": total_requests,
            }

    def reset_stats(self) -> None:
        """Reinicia las estadísticas."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._invalidations = 0


# Singleton global
_global_cache: Optional[MetadataCache] = None


def get_metadata_cache() -> MetadataCache:
    """Obtiene la instancia global del caché de metadatos."""
    global _global_cache
    if _global_cache is None:
        _global_cache = MetadataCache()
    return _global_cache


def reset_global_cache() -> None:
    """Reinicia la instancia global del caché (útil para tests)."""
    global _global_cache
    _global_cache = None


__all__ = ["MetadataCache", "get_metadata_cache", "reset_global_cache"]
