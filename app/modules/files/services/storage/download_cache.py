
from __future__ import annotations
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/download_cache.py

Cache de descargas con optimizaciones:
- LRU + TTL para gestión de memoria
- Compresión automática para archivos grandes
- Métricas de rendimiento
- Compatible con EnhancedCache para producción

Constructor esperado por tests (mantiene compatibilidad):
    DownloadCache(max_entries: int = 256, ttl_seconds: int = 300)

Métodos:
    - set(key: str, value: bytes) -> None
    - get(key: str) -> Optional[bytes]
    - invalidate(key: str) -> None
    - clear() -> None
    - get_or_cache(key: str, fetcher: Callable[[], bytes]) -> bytes

Autor: Ixchel Beristain / DoxAI
Fecha: 04/11/2025 (optimizado: 05/11/2025)
"""

import time
from collections import OrderedDict
from typing import Callable, Optional
import logging

# Importar cache mejorado si está disponible
try:
    from .enhanced_cache import EnhancedCache
    ENHANCED_CACHE_AVAILABLE = True
except ImportError:
    ENHANCED_CACHE_AVAILABLE = False

logger = logging.getLogger(__name__)


class DownloadCache:
    """
    Cache de descargas optimizado.
    
    En producción usa EnhancedCache si está disponible, de lo contrario
    usa implementación básica (para tests y compatibilidad).
    """
    
    def __init__(
        self,
        max_entries: int = 256,
        ttl_seconds: int = 300,
        enable_compression: bool = True,
        enable_metrics: bool = False,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries debe ser > 0")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser > 0")
        
        self.max_entries = max_entries
        self.ttl = ttl_seconds
        
        # Usar cache mejorado si está disponible
        if ENHANCED_CACHE_AVAILABLE and enable_compression:
            try:
                self._enhanced_cache = EnhancedCache(
                    max_entries_l1=max_entries,
                    ttl_seconds=ttl_seconds,
                    enable_compression=enable_compression,
                    enable_metrics=enable_metrics,
                )
                logger.info(
                    f"🚀 DownloadCache initialized with EnhancedCache "
                    f"(compression={enable_compression}, metrics={enable_metrics})"
                )
                self._use_enhanced = True
            except Exception as e:
                logger.warning(f"Could not initialize EnhancedCache: {e}, using basic cache")
                self._use_enhanced = False
                self._enhanced_cache = None
        else:
            self._use_enhanced = False
            self._enhanced_cache = None
        
        # Cache básico (fallback)
        self._store: "OrderedDict[str, tuple[float, bytes]]" = OrderedDict()

    def _now(self) -> float:
        return time.time()

    def _is_expired(self, ts: float) -> bool:
        return (self._now() - ts) > self.ttl

    def _evict_if_needed(self) -> None:
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def set(self, key: str, value: bytes) -> None:
        """Almacena un valor en el cache."""
        if self._use_enhanced and self._enhanced_cache:
            self._enhanced_cache.set(key, value)
        else:
            self._store[key] = (self._now(), value)
            self._store.move_to_end(key, last=True)
            self._evict_if_needed()

    def get(self, key: str) -> Optional[bytes]:
        """Obtiene un valor del cache."""
        if self._use_enhanced and self._enhanced_cache:
            return self._enhanced_cache.get(key)
        else:
            item = self._store.get(key)
            if not item:
                return None
            ts, val = item
            if self._is_expired(ts):
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key, last=True)
            return val

    def invalidate(self, key: str) -> None:
        """Invalida una entrada del cache."""
        if self._use_enhanced and self._enhanced_cache:
            self._enhanced_cache.invalidate(key)
        else:
            self._store.pop(key, None)

    def clear(self) -> None:
        """Limpia todo el cache."""
        if self._use_enhanced and self._enhanced_cache:
            self._enhanced_cache.clear()
        else:
            self._store.clear()

    def _coerce_bytes(self, data) -> bytes:
        if data is None:
            return b""
        if isinstance(data, bytes):
            return data
        if isinstance(data, (bytearray, memoryview)):
            return bytes(data)
        if isinstance(data, str):
            return data.encode("utf-8")
        read = getattr(data, "read", None)
        if callable(read):
            chunk = read()
            if chunk is None:
                return b""
            if isinstance(chunk, str):
                return chunk.encode("utf-8")
            if isinstance(chunk, bytes):
                return chunk
            return bytes(chunk)
        try:
            return bytes(data)
        except Exception:
            return b""

    async def get_or_cache(self, key: str, fetcher: Callable[[], bytes]) -> bytes:
        """
        Obtiene valor del cache o ejecuta fetcher si no existe/expiró.
        Soporta fetchers sync y async.
        """
        if self._use_enhanced and self._enhanced_cache:
            return await self._enhanced_cache.get_or_cache(key, fetcher)
        else:
            found = self.get(key)
            if found is not None:
                return found
            
            # Ejecutar fetcher (puede ser sync o async)
            import inspect
            data = fetcher()
            
            # Si es awaitable, usar await directamente
            if inspect.isawaitable(data):
                data = await data  # type: ignore
            
            data_b = self._coerce_bytes(data)
            self.set(key, data_b)
            return data_b
    
    def get_metrics(self):
        """Retorna métricas del cache si está disponible."""
        if self._use_enhanced and self._enhanced_cache:
            return self._enhanced_cache.get_metrics()
        return None
    
    def log_metrics(self) -> None:
        """Registra métricas del cache."""
        if self._use_enhanced and self._enhanced_cache:
            self._enhanced_cache.log_metrics()
    
    def __contains__(self, key: str) -> bool:
        """Verifica si una clave existe en el cache."""
        if self._use_enhanced and self._enhanced_cache:
            return key in self._enhanced_cache
        return key in self._store
    
    def __len__(self) -> int:
        """Retorna el número de entradas en el cache."""
        if self._use_enhanced and self._enhanced_cache:
            return len(self._enhanced_cache)
        return len(self._store)

# Fin del archivo backend\app\modules\files\services\storage\download_cache.py






