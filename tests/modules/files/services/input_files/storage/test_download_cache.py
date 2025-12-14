
# tests/modules/files/services/input_files/storage/test_download_cache.py
# -*- coding: utf-8 -*-
"""
Tests para el caché de descargas (DownloadCache).

Contrato asumido (laxo para maximizar compatibilidad):
- Constructor: DownloadCache(max_entries: int = 128, ttl_seconds: int | float = 300)
- Métodos principales:
    - get(key: str) -> bytes | None
    - set(key: str, value: bytes) -> None
    - get_or_cache(key: str, fetcher: Callable[[], bytes|awaitable]) -> bytes
    - invalidate(key: str) -> None
    - clear() -> None
    - __contains__(key) -> bool  (opcional)
    - __len__() -> int           (opcional)
- Comportamiento:
    - TTL: entradas expiran después de ttl_seconds.
    - Capacidad: al superar max_entries, el caché expulsa alguna(s) entradas (LRU o similar).
    - get_or_cache: llama al fetcher sólo si la clave no está o está expirada.
"""

import inspect
import asyncio
import pytest
from time import monotonic

from app.modules.files.services.storage.download_cache import DownloadCache


async def _maybe_await(v):
    """Permite consumir APIs sync/async de forma transparente."""
    return await v if inspect.isawaitable(v) else v


@pytest.mark.asyncio
async def test_set_get_happy_path_bytes_preserved():
    cache = DownloadCache(max_entries=8, ttl_seconds=60)
    key = "users/u1/projects/1/input/a.txt"
    value = b"Hola DoxAI"

    # set/get
    set_r = cache.set(key, value)
    got = cache.get(key)
    got = await _maybe_await(got)

    assert got == value
    assert key in cache if hasattr(cache, "__contains__") else True
    assert (len(cache) >= 1) if hasattr(cache, "__len__") else True


@pytest.mark.asyncio
async def test_get_or_cache_calls_fetcher_once_and_memoizes():
    cache = DownloadCache(max_entries=8, ttl_seconds=60)
    key = "users/u2/projects/2/input/b.bin"
    payload = b"\x00" * 1024
    calls = {"n": 0}

    async def fetcher():
        calls["n"] += 1
        await asyncio.sleep(0)  # cede control para simular IO
        return payload

    # Primera vez invoca fetcher
    v1 = await cache.get_or_cache(key, fetcher)
    assert v1 == payload
    assert calls["n"] == 1

    # Segunda vez debe venir del caché (no invoca)
    v2 = await cache.get_or_cache(key, fetcher)
    assert v2 == payload
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_ttl_expiration_expires_entry():
    cache = DownloadCache(max_entries=8, ttl_seconds=0.2)  # 200 ms
    key = "users/u3/projects/3/input/c.csv"
    cache.set(key, b"123,456")

    # Inmediato: existe
    assert await _maybe_await(cache.get(key)) == b"123,456"

    # Espera a que expire
    await asyncio.sleep(0.25)
    expired = await _maybe_await(cache.get(key))
    assert expired is None, "La entrada debe expirar después del TTL"


@pytest.mark.asyncio
async def test_invalidate_removes_entry():
    cache = DownloadCache(max_entries=8, ttl_seconds=60)
    key = "users/u4/projects/4/input/d.json"
    cache.set(key, b"{}")

    assert await _maybe_await(cache.get(key)) == b"{}"
    cache.invalidate(key)
    assert await _maybe_await(cache.get(key)) is None
    assert (key not in cache) if hasattr(cache, "__contains__") else True


@pytest.mark.asyncio
async def test_clear_empties_cache():
    cache = DownloadCache(max_entries=8, ttl_seconds=60)
    for i in range(5):
        cache.set(f"k{i}", f"v{i}".encode())

    if hasattr(cache, "__len__"):
        assert len(cache) == 5

    cache.clear()
    # Todas deben faltar
    for i in range(5):
        assert await _maybe_await(cache.get(f"k{i}")) is None
    if hasattr(cache, "__len__"):
        assert len(cache) == 0


@pytest.mark.asyncio
async def test_capacity_eviction_keeps_recent_entries():
    """
    Al exceder max_entries, el caché debe expulsar alguna(s) entradas antiguas.
    No forzamos política exacta (LRU/MRU), pero validamos que:
      - La capacidad efectiva no exceda max_entries.
      - Alguna de las entradas más antiguas ya no esté.
      - La última insertada sí esté.
    """
    max_entries = 4
    cache = DownloadCache(max_entries=max_entries, ttl_seconds=60)

    inserted = []
    for i in range(6):
        k = f"key{i}"
        cache.set(k, f"val{i}".encode())
        inserted.append(k)

    # Última debe permanecer
    last_key = inserted[-1]
    assert await _maybe_await(cache.get(last_key)) == b"val5"

    # Alguna de las primeras probablemente fue expulsada
    oldest_candidates = inserted[:2]
    evicted_or_none = [await _maybe_await(cache.get(k)) for k in oldest_candidates]
    assert any(v is None for v in evicted_or_none), "Se espera expulsión de alguna entrada antigua"

    # La ocupación no debe exceder max_entries (si __len__ está disponible)
    if hasattr(cache, "__len__"):
        assert len(cache) <= max_entries


@pytest.mark.asyncio
async def test_get_or_cache_respects_ttl_and_refetches_on_expiry():
    """
    Si la entrada expira, get_or_cache debe volver a invocar al fetcher.
    """
    cache = DownloadCache(max_entries=8, ttl_seconds=0.15)
    key = "users/u5/projects/5/input/e.bin"
    calls = {"n": 0}

    async def fetcher():
        calls["n"] += 1
        return b"DATA"

    v1 = await cache.get_or_cache(key, fetcher)
    assert v1 == b"DATA"
    assert calls["n"] == 1

    # Espera a que expire
    await asyncio.sleep(0.2)

    v2 = await cache.get_or_cache(key, fetcher)
    assert v2 == b"DATA"
    assert calls["n"] == 2, "Debe refetchear después del TTL"


# Fin del archivo tests/modules/files/services/input_files/storage/test_download_cache.py
