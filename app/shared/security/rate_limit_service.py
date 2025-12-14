
# -*- coding: utf-8 -*-
"""
backend/app/shared/security/rate_limit_service.py

Rate limiting basado en Redis con fallback in-memory.
Usado para limitar intentos de login y proteger endpoints sensibles.

Autor: Ixchel Beristain
Actualizado: 18/10/2025
"""
from __future__ import annotations
import os, time
from typing import Optional

try:
    import redis
except Exception:
    redis = None

class RateLimiter:
    def __init__(self, prefix: str = "doxai:rl:", window_sec: int = 60, max_hits: int = 5):
        self.prefix = prefix
        self.window_sec = window_sec
        self.max_hits = max_hits
        self._mem = {}  # fallback local: {key: [(timestamp, ...)]}

        url = os.getenv("REDIS_URL")
        self._r = None
        if redis and url:
            try:
                self._r = redis.from_url(url, decode_responses=True)
            except Exception:
                self._r = None

    def _key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def hit(self, key: str) -> bool:
        """
        Registra un intento y devuelve True si **supera** el límite (bloquear).
        """
        if self._r:
            k = self._key(key)
            pipe = self._r.pipeline()
            pipe.incr(k, 1)
            pipe.expire(k, self.window_sec)
            hits, _ = pipe.execute()
            return int(hits) > self.max_hits

        # Fallback in-memory
        now = time.time()
        lst = self._mem.get(key, [])
        lst = [t for t in lst if now - t < self.window_sec]
        lst.append(now)
        self._mem[key] = lst
        return len(lst) > self.max_hits
# Fin del archivo