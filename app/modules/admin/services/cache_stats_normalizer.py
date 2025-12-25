# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/services/cache_stats_normalizer.py

Normalizador de estadísticas de caché para garantizar un contrato consistente.

Autor: DoxAI
Fecha: 2025-12-22
"""

from typing import Any, Dict


def normalize_cache_stats(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza las estadísticas crudas del caché a un formato consistente.
    
    Garantiza que todas las llaves esperadas existan con valores por defecto
    razonables si no están presentes en el input.
    
    Args:
        raw: Diccionario con stats crudas del cache (puede tener llaves faltantes)
    
    Returns:
        Diccionario normalizado con todas las llaves garantizadas:
        - size: int
        - max_size: int
        - hits: int
        - misses: int
        - evictions: int
        - invalidations: int
        - hit_rate: float (porcentaje 0-100)
        - total_requests: int
    """
    hits = raw.get("hits", 0)
    misses = raw.get("misses", 0)
    total_requests = raw.get("total_requests", hits + misses)
    
    # hit_rate puede venir como "hit_rate", "hit_rate_percent", o calcularse
    if "hit_rate" in raw:
        hit_rate = float(raw["hit_rate"])
    elif "hit_rate_percent" in raw:
        hit_rate = float(raw["hit_rate_percent"])
    elif total_requests > 0:
        hit_rate = (hits / total_requests) * 100
    else:
        hit_rate = 0.0
    
    return {
        "size": raw.get("size", 0),
        "max_size": raw.get("max_size", 0),
        "hits": hits,
        "misses": misses,
        "evictions": raw.get("evictions", 0),
        "invalidations": raw.get("invalidations", 0),
        "hit_rate": round(hit_rate, 2),
        "total_requests": total_requests,
    }


__all__ = ["normalize_cache_stats"]
