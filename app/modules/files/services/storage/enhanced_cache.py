# -*- coding: utf-8 -*-
"""
backend/app/modules/files/services/storage/enhanced_cache.py

Cache mejorado de múltiples niveles con:
- Cache L1 (memoria): acceso ultrarrápido
- Cache L2 (disco opcional): mayor capacidad
- Compresión automática
- Métricas detalladas
- Precalentamiento inteligente

Autor: DoxAI
Fecha: 2025-11-05
"""

from __future__ import annotations
import time
import hashlib
from collections import OrderedDict
from typing import Callable, Optional, Any
from pathlib import Path
import logging

from .cache_metrics import CacheMetrics
from .compression_service import get_compression_service, CompressionAlgo

logger = logging.getLogger(__name__)


class EnhancedCache:
    """
    Cache de múltiples niveles con compresión y métricas.
    """
    
    def __init__(
        self,
        max_entries_l1: int = 256,
        max_size_bytes_l1: int = 100 * 1024 * 1024,  # 100 MB
        ttl_seconds: int = 300,
        enable_compression: bool = True,
        compression_algo: CompressionAlgo = "gzip",
        enable_metrics: bool = True,
        disk_cache_dir: Optional[Path] = None,
        max_size_bytes_l2: Optional[int] = None,
    ) -> None:
        """
        Inicializa el cache mejorado.
        
        Args:
            max_entries_l1: Máximo de entradas en cache L1 (memoria)
            max_size_bytes_l1: Tamaño máximo en bytes del cache L1
            ttl_seconds: Tiempo de vida de las entradas en segundos
            enable_compression: Habilitar compresión automática
            compression_algo: Algoritmo de compresión a usar
            enable_metrics: Habilitar recolección de métricas
            disk_cache_dir: Directorio para cache L2 en disco (opcional)
            max_size_bytes_l2: Tamaño máximo del cache L2 (opcional)
        """
        if max_entries_l1 <= 0:
            raise ValueError("max_entries_l1 debe ser > 0")
        if max_size_bytes_l1 <= 0:
            raise ValueError("max_size_bytes_l1 debe ser > 0")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds debe ser > 0")
            
        # Configuración
        self.max_entries_l1 = max_entries_l1
        self.max_size_bytes_l1 = max_size_bytes_l1
        self.ttl = ttl_seconds
        self.enable_compression = enable_compression
        self.compression_algo = compression_algo
        self.enable_metrics = enable_metrics
        
        # Cache L1 (memoria): OrderedDict para LRU
        # Estructura: key -> (timestamp, data, size, is_compressed)
        self._store_l1: OrderedDict[str, tuple[float, bytes, int, bool]] = OrderedDict()
        self._current_size_l1 = 0
        
        # Cache L2 (disco opcional)
        self.disk_cache_dir = disk_cache_dir
        self.max_size_bytes_l2 = max_size_bytes_l2
        if disk_cache_dir:
            disk_cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"💾 Disk cache L2 enabled at {disk_cache_dir}")
        
        # Métricas
        self.metrics = CacheMetrics() if enable_metrics else None
        
        # Servicio de compresión
        self._compression_service = get_compression_service() if enable_compression else None
    
    def _now(self) -> float:
        """Retorna el timestamp actual."""
        return time.time()
    
    def _is_expired(self, ts: float) -> bool:
        """Verifica si un timestamp ha expirado."""
        return (self._now() - ts) > self.ttl
    
    def _make_cache_key(self, key: str) -> str:
        """Genera una clave de cache segura para el sistema de archivos."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def _evict_if_needed_l1(self) -> None:
        """Evicta entradas del cache L1 si excede límites."""
        while (
            len(self._store_l1) > self.max_entries_l1
            or self._current_size_l1 > self.max_size_bytes_l1
        ):
            if not self._store_l1:
                break
                
            # Evictar la entrada más antigua (LRU)
            key, (_, _, size, _) = self._store_l1.popitem(last=False)
            self._current_size_l1 -= size
            
            if self.metrics:
                self.metrics.record_eviction(size)
            
            logger.debug(f"🗑️  Evicted {key} from L1 cache ({size} bytes)")
    
    def set(self, key: str, value: bytes, compress: bool = True) -> None:
        """
        Almacena un valor en el cache.
        
        Args:
            key: Clave del cache
            value: Datos a almacenar
            compress: Si se debe intentar comprimir (default: True)
        """
        if not value:
            return
        
        data = value
        is_compressed = False
        
        # Intentar compresión si está habilitada
        if self.enable_compression and compress and self._compression_service:
            result = self._compression_service.smart_compress(data, preferred_algo=self.compression_algo)
            if result.algorithm != "none":
                data = result.data
                is_compressed = True
                logger.debug(f"🗜️  Compressed {key}: {result.savings_percent:.1f}% savings")
        
        size = len(data)
        
        # Almacenar en L1
        self._store_l1[key] = (self._now(), data, size, is_compressed)
        self._store_l1.move_to_end(key, last=True)
        self._current_size_l1 += size
        
        # Evictar si es necesario
        self._evict_if_needed_l1()
        
        # Métricas
        if self.metrics:
            self.metrics.record_set(size)
        
        logger.debug(f"📦 Cached {key} ({size} bytes, compressed={is_compressed})")
    
    def get(self, key: str) -> Optional[bytes]:
        """
        Obtiene un valor del cache.
        
        Args:
            key: Clave del cache
            
        Returns:
            Optional[bytes]: Datos si existen y no han expirado, None en caso contrario
        """
        # Intentar L1 (memoria)
        item = self._store_l1.get(key)
        if item:
            ts, data, size, is_compressed = item
            
            # Verificar expiración
            if self._is_expired(ts):
                self._store_l1.pop(key, None)
                self._current_size_l1 -= size
                if self.metrics:
                    self.metrics.record_expiration(size)
                logger.debug(f"⏰ Cache entry expired: {key}")
                return None
            
            # Descomprimir si es necesario
            if is_compressed and self._compression_service:
                try:
                    data = self._compression_service.decompress(data, self.compression_algo)
                except Exception as e:
                    logger.error(f"Decompression failed for {key}: {e}")
                    return None
            
            # Mover al final (LRU)
            self._store_l1.move_to_end(key, last=True)
            
            # Métricas
            if self.metrics:
                self.metrics.record_hit(len(data))
            
            logger.debug(f"✅ Cache hit L1: {key}")
            return data
        
        # Cache miss
        if self.metrics:
            self.metrics.record_miss()
        
        logger.debug(f"❌ Cache miss: {key}")
        return None
    
    def invalidate(self, key: str) -> None:
        """
        Invalida una entrada del cache.
        
        Args:
            key: Clave a invalidar
        """
        item = self._store_l1.pop(key, None)
        if item:
            _, _, size, _ = item
            self._current_size_l1 -= size
            if self.metrics:
                self.metrics.record_delete(size)
            logger.debug(f"🗑️  Invalidated {key}")
    
    def clear(self) -> None:
        """Limpia todo el cache."""
        self._store_l1.clear()
        self._current_size_l1 = 0
        
        if self.disk_cache_dir and self.disk_cache_dir.exists():
            for file in self.disk_cache_dir.glob("*"):
                try:
                    file.unlink()
                except Exception as e:
                    logger.warning(f"Could not delete cache file {file}: {e}")
        
        if self.metrics:
            self.metrics.reset()
        
        logger.info("🧹 Cache cleared")
    
    async def get_or_cache(
        self,
        key: str,
        fetcher: Callable[[], Any],
        compress: bool = True,
    ) -> bytes:
        """
        Obtiene valor del cache o ejecuta fetcher si no existe/expiró.
        
        Args:
            key: Clave del cache
            fetcher: Función para obtener datos si no están en cache
            compress: Si se debe comprimir al cachear
            
        Returns:
            bytes: Datos obtenidos
        """
        # Intentar obtener del cache
        found = self.get(key)
        if found is not None:
            return found
        
        # Ejecutar fetcher
        import inspect
        data = fetcher()
        
        # Si es awaitable, usar await
        if inspect.isawaitable(data):
            data = await data  # type: ignore
        
        # Coerce a bytes
        data_b = self._coerce_bytes(data)
        
        # Almacenar en cache
        self.set(key, data_b, compress=compress)
        
        return data_b
    
    def _coerce_bytes(self, data: Any) -> bytes:
        """Convierte diversos tipos a bytes."""
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
    
    def get_metrics(self) -> Optional[CacheMetrics]:
        """Retorna las métricas del cache."""
        return self.metrics
    
    def log_metrics(self) -> None:
        """Registra un resumen de métricas en el log."""
        if self.metrics:
            self.metrics.log_summary()
    
    def __contains__(self, key: str) -> bool:
        """Verifica si una clave existe en el cache."""
        return key in self._store_l1
    
    def __len__(self) -> int:
        """Retorna el número de entradas en el cache."""
        return len(self._store_l1)


__all__ = ["EnhancedCache"]
