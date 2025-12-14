# -*- coding: utf-8 -*-
"""
tests/modules/files/services/cache/test_metadata_cache.py

Tests para el sistema de caché de metadatos.

Cubre:
- Operaciones básicas: get/set/invalidate
- TTL y expiración
- LRU eviction
- Thread safety
- Estadísticas
- Invalidación por patrón
"""

import pytest
import time
import threading
from datetime import datetime, timedelta

from app.modules.files.services.cache import MetadataCache


@pytest.fixture
def cache():
    """Caché limpio para cada test."""
    return MetadataCache(max_size=10, default_ttl=2, enable_stats=True)


def test_cache_set_and_get(cache):
    """Debe almacenar y recuperar valores."""
    cache.set("key1", {"data": "value1"})
    result = cache.get("key1")
    assert result is not None
    assert result["data"] == "value1"


def test_cache_miss_returns_none(cache):
    """Debe retornar None si la clave no existe."""
    result = cache.get("nonexistent")
    assert result is None


def test_cache_ttl_expiration(cache):
    """Las entradas deben expirar después del TTL."""
    cache.set("key1", "value1", ttl=1)
    
    # Inmediatamente después debe estar disponible
    assert cache.get("key1") == "value1"
    
    # Después del TTL debe expirar
    time.sleep(1.5)
    assert cache.get("key1") is None


def test_cache_lru_eviction(cache):
    """Debe remover la entrada menos usada cuando se llena."""
    # Llenar el caché (max_size=10)
    for i in range(10):
        cache.set(f"key{i}", f"value{i}")
    
    # Acceder a todas excepto key0 para que sea LRU
    for i in range(1, 10):
        cache.get(f"key{i}")
    
    # Agregar una más, debería evict key0
    cache.set("key10", "value10")
    
    assert cache.get("key0") is None
    assert cache.get("key10") == "value10"


def test_cache_invalidate(cache):
    """Debe invalidar una entrada específica."""
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    
    invalidated = cache.invalidate("key1")
    assert invalidated is True
    assert cache.get("key1") is None
    
    # Invalidar clave inexistente
    invalidated = cache.invalidate("nonexistent")
    assert invalidated is False


def test_cache_invalidate_pattern(cache):
    """Debe invalidar todas las entradas con un prefijo."""
    cache.set("input:1", "value1")
    cache.set("input:2", "value2")
    cache.set("product:1", "value3")
    cache.set("product:2", "value4")
    
    count = cache.invalidate_pattern("input:")
    assert count == 2
    
    assert cache.get("input:1") is None
    assert cache.get("input:2") is None
    assert cache.get("product:1") == "value3"
    assert cache.get("product:2") == "value4"


def test_cache_clear(cache):
    """Debe limpiar todo el caché."""
    for i in range(5):
        cache.set(f"key{i}", f"value{i}")
    
    cache.clear()
    
    for i in range(5):
        assert cache.get(f"key{i}") is None


def test_cache_stats(cache):
    """Debe rastrear estadísticas correctamente."""
    # Inicialmente vacío
    stats = cache.get_stats()
    assert stats["size"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    
    # Set y get (hit)
    cache.set("key1", "value1")
    cache.get("key1")
    
    stats = cache.get_stats()
    assert stats["size"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 0
    
    # Miss
    cache.get("nonexistent")
    
    stats = cache.get_stats()
    assert stats["misses"] == 1
    assert stats["hit_rate_percent"] == 50.0


def test_cache_stats_evictions(cache):
    """Debe rastrear evictions cuando se llena."""
    # Llenar más allá del límite
    for i in range(15):
        cache.set(f"key{i}", f"value{i}")
    
    stats = cache.get_stats()
    assert stats["evictions"] == 5  # 15 - 10 (max_size)


def test_cache_stats_invalidations(cache):
    """Debe rastrear invalidaciones."""
    cache.set("key1", "value1")
    cache.set("key2", "value2")
    
    cache.invalidate("key1")
    cache.invalidate_pattern("key")
    
    stats = cache.get_stats()
    assert stats["invalidations"] == 2  # 1 + 1


def test_cache_reset_stats(cache):
    """Debe reiniciar estadísticas."""
    cache.set("key1", "value1")
    cache.get("key1")
    cache.get("nonexistent")
    
    cache.reset_stats()
    
    stats = cache.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0


def test_cache_thread_safety():
    """El caché debe ser thread-safe."""
    cache = MetadataCache(max_size=100, default_ttl=10)
    errors = []
    
    def worker(thread_id):
        try:
            for i in range(50):
                key = f"thread{thread_id}_key{i}"
                cache.set(key, f"value{i}")
                value = cache.get(key)
                assert value == f"value{i}"
        except Exception as e:
            errors.append(e)
    
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    assert len(errors) == 0
    stats = cache.get_stats()
    assert stats["size"] <= 100


def test_cache_update_existing_key(cache):
    """Debe actualizar el valor de una clave existente."""
    cache.set("key1", "value1")
    cache.set("key1", "value2")
    
    result = cache.get("key1")
    assert result == "value2"
    
    # No debe incrementar el tamaño
    stats = cache.get_stats()
    assert stats["size"] == 1


def test_cache_custom_ttl(cache):
    """Debe respetar TTL personalizado por entrada."""
    cache.set("key1", "value1", ttl=1)
    cache.set("key2", "value2", ttl=3)
    
    time.sleep(1.5)
    
    assert cache.get("key1") is None  # Expiró
    assert cache.get("key2") == "value2"  # Aún válido


def test_cache_entry_moves_to_end_on_access(cache):
    """Acceder a una entrada debe moverla al final (LRU)."""
    # Llenar caché
    for i in range(10):
        cache.set(f"key{i}", f"value{i}")
    
    # Acceder a key0 varias veces
    for _ in range(3):
        cache.get("key0")
    
    # Agregar nueva entrada, debería evict key1 (no key0)
    cache.set("key10", "value10")
    
    assert cache.get("key0") == "value0"  # Todavía existe
    assert cache.get("key1") is None  # Fue evicted


# Fin del archivo tests/modules/files/services/cache/test_metadata_cache.py
