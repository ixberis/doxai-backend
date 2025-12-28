# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/cache/metadata_cache.py

Sistema de caché en memoria para metadatos con TTL y LRU eviction.

Implementa CacheBackend para garantizar consistencia con otros cachés del sistema.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

from app.shared.cache.cache_backend import CacheBackend

logger = logging.getLogger(__name__)


class MetadataCache(CacheBackend):
    """
    Caché thread-safe con TTL y LRU eviction.
    
    Implementa la interfaz CacheBackend con soporte para:
    - TTL configurable por entrada (ttl=None para no expirar)
    - LRU eviction cuando se alcanza max_size (si max_size no es None)
    - Métricas separadas: expiraciones vs invalidaciones explícitas
    
    Política de TTL:
    - ttl=None en set(): Usa default_ttl del cache
    - ttl=0: La entrada NO se almacena (política: "no cachear")
    - ttl<0: La entrada NO se almacena (política: "no cachear")
    - default_ttl=None en constructor: Entradas nunca expiran por defecto
    
    Arquitectura:
    Este caché es un L1 in-memory por proceso. En futuras iteraciones,
    RedisCacheBackend actuará como L2 para RAG y otros casos de uso distribuido.
    """

    def __init__(
        self,
        max_size: Optional[int] = 1000,
        default_ttl: Optional[int] = 3600,
        enable_stats: bool = True,
        name: str = "metadata",
    ):
        """
        Inicializa el caché.
        
        Args:
            max_size: Máximo número de entradas. None = sin límite.
            default_ttl: TTL por defecto en segundos. None = no expira por defecto.
            enable_stats: Si se recolectan estadísticas
            name: Nombre identificador del caché (para logs/métricas)
        """
        self._max_size = max_size
        self._default_ttl = default_ttl
        self.enable_stats = enable_stats
        self.name = name
        
        self._cache: OrderedDict[str, tuple[Any, Optional[float]]] = OrderedDict()
        self._lock = threading.RLock()
        
        # Estadísticas
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0
        self._expired_removals = 0  # Nuevo: contador de expiraciones

    @property
    def max_size(self) -> Optional[int]:
        """Tamaño máximo del caché."""
        return self._max_size

    @property
    def default_ttl(self) -> Optional[int]:
        """TTL por defecto en segundos. None si no expira por defecto."""
        return self._default_ttl

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
                    self._expired_removals += 1  # Contar expiración
                return None

            # Mover al final (LRU)
            self._cache.move_to_end(key)
            
            if self.enable_stats:
                self._hits += 1
            
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Almacena un valor en el caché.
        
        Política de TTL:
        - ttl=None: Usa default_ttl. Si default_ttl también es None, no expira.
        - ttl=0 o ttl<0: NO almacena la entrada (no cachear).
        - ttl>0: Expira después de ttl segundos.
        """
        # Política: ttl <= 0 significa "no cachear"
        if ttl is not None and ttl <= 0:
            logger.debug(f"[{self.name}] set({key}): ttl={ttl} <= 0, not caching")
            return
        
        with self._lock:
            # Determinar expiry
            if ttl is not None:
                expiry: Optional[float] = time.time() + ttl
            elif self._default_ttl is not None:
                expiry = time.time() + self._default_ttl
            else:
                expiry = None  # No expira

            # Si existe, actualizar
            if key in self._cache:
                self._cache[key] = (value, expiry)
                self._cache.move_to_end(key)
                return

            # Verificar límite de tamaño (si max_size está definido)
            if self._max_size is not None and len(self._cache) >= self._max_size:
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
            
            # Incrementar contador de expiraciones
            if self.enable_stats:
                self._expired_removals += len(expired_keys)
            
            # Log agregado de entradas malformadas (rate-limited: 1x por cleanup)
            if malformed_count > 0:
                logger.warning(
                    "[%s] cleanup detected %d malformed entries (samples: %s). "
                    "Expected format: (value, expiry). Entries preserved but may indicate corruption.",
                    self.name,
                    malformed_count,
                    ", ".join(malformed_samples),
                )
            
            return len(expired_keys)

    def get_stats(self) -> dict:
        """Retorna estadísticas del caché según CacheBackend."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0
            
            return {
                "name": self.name,
                "size": len(self._cache),
                "max_size": self._max_size,
                "default_ttl": self._default_ttl,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "invalidations": self._invalidations,
                "expired_removals": self._expired_removals,
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
            self._expired_removals = 0


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
