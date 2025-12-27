# -*- coding: utf-8 -*-
"""
backend/app/shared/scheduler/jobs/cache_cleanup_job.py

Job programado para limpieza automática de cachés.

Ejecuta limpieza periódica, eliminando entradas expiradas y registrando estadísticas.
Diseñado para ser genérico y reutilizable con cualquier implementación de CacheBackend.

Autor: DoxAI
Fecha: 2025-11-05
Actualizado: 2025-12-27 - Refactor para soportar múltiples cachés (Files, RAG, etc.)
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List

from app.shared.cache import CacheBackend

logger = logging.getLogger(__name__)


async def cleanup_cache(
    cache: CacheBackend,
    cache_name: str,
) -> Dict[str, Any]:
    """
    Limpia entradas expiradas de un caché específico.
    
    Args:
        cache: Instancia del caché (debe implementar CacheBackend)
        cache_name: Nombre identificador para logs
        
    Returns:
        Dict con estadísticas de la limpieza
    """
    start_time = datetime.utcnow()
    
    try:
        # Estadísticas previas
        stats_before = cache.get_stats()
        entries_before = stats_before.get("size", 0)
        
        # Ejecutar limpieza
        removed_count = cache.cleanup()
        
        # Estadísticas posteriores
        stats_after = cache.get_stats()
        entries_after = stats_after.get("size", 0)
        
        # Calcular duración
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        result = {
            "cache_name": cache_name,
            "timestamp": start_time.isoformat(),
            "entries_before": entries_before,
            "entries_after": entries_after,
            "removed_expired": removed_count,
            "duration_ms": round(duration_ms, 2),
            "hit_rate_percent": stats_after.get("hit_rate_percent", 0.0),
            "evictions": stats_after.get("evictions", 0),
            "expired_removals": stats_after.get("expired_removals", 0),
            "invalidations": stats_after.get("invalidations", 0),
        }
        
        # Log INFO siempre con métricas clave
        logger.info(
            "[cache_cleanup] cache=%s entries_before=%d entries_after=%d "
            "removed_expired=%d duration_ms=%.2f hit_rate=%.1f%% "
            "evictions=%d expired_removals=%d",
            cache_name,
            entries_before,
            entries_after,
            removed_count,
            result["duration_ms"],
            result["hit_rate_percent"],
            result["evictions"],
            result["expired_removals"],
        )
        
        # Advertencia si el caché está muy lleno
        max_size = cache.max_size
        if max_size and entries_after > max_size * 0.9:
            logger.warning(
                "[cache_cleanup] cache=%s at %.1f%% capacity (%d/%d). "
                "Consider increasing max_size or reducing TTL.",
                cache_name,
                (entries_after / max_size) * 100,
                entries_after,
                max_size,
            )
        
        # Advertencia si el hit rate es bajo
        total_requests = stats_after.get("total_requests", 0)
        if total_requests > 100 and result["hit_rate_percent"] < 60:
            logger.warning(
                "[cache_cleanup] cache=%s low hit rate (%.1f%%). "
                "Cache may not be effective. hits=%d misses=%d",
                cache_name,
                result["hit_rate_percent"],
                stats_after.get("hits", 0),
                stats_after.get("misses", 0),
            )
        
        return result
        
    except Exception as e:
        logger.error(
            "[cache_cleanup] cache=%s error: %s",
            cache_name,
            str(e),
            exc_info=True,
        )
        return {
            "cache_name": cache_name,
            "timestamp": start_time.isoformat(),
            "error": str(e),
            "removed_expired": 0,
        }


async def cleanup_all_caches(
    cache_providers: List[Callable[[], CacheBackend]],
) -> Dict[str, Any]:
    """
    Limpia todos los cachés registrados.
    
    Args:
        cache_providers: Lista de funciones que retornan instancias de caché
        
    Returns:
        Dict con estadísticas agregadas de todas las limpiezas
    """
    start_time = datetime.utcnow()
    results: List[Dict[str, Any]] = []
    total_removed = 0
    
    for provider in cache_providers:
        try:
            cache = provider()
            # Obtener nombre del caché de sus stats o usar fallback
            stats = cache.get_stats()
            cache_name = stats.get("name", "unknown")
            
            result = await cleanup_cache(cache, cache_name)
            results.append(result)
            total_removed += result.get("removed_expired", 0)
        except Exception as e:
            logger.error(
                "[cache_cleanup] Failed to get cache from provider: %s",
                str(e),
                exc_info=True,
            )
    
    end_time = datetime.utcnow()
    duration_ms = (end_time - start_time).total_seconds() * 1000
    
    return {
        "timestamp": start_time.isoformat(),
        "caches_cleaned": len(results),
        "total_removed": total_removed,
        "duration_ms": round(duration_ms, 2),
        "results": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Backward compatibility: cleanup del MetadataCache global
# ─────────────────────────────────────────────────────────────────────────────

async def cleanup_expired_cache() -> Dict[str, Any]:
    """
    Limpia entradas expiradas del caché de metadatos (Files).
    
    Mantiene backward compatibility con el scheduler existente.
    
    Returns:
        Dict con estadísticas de la limpieza
    """
    from app.modules.files.services.cache import get_metadata_cache
    
    cache = get_metadata_cache()
    return await cleanup_cache(cache, "metadata")


def register_cache_cleanup_job(scheduler) -> str:
    """
    Registra el job de limpieza de caché en el scheduler.
    
    El job se ejecutará cada hora (intervalo desde el arranque del proceso,
    no sincronizado con el "top of the hour"). Para cron real, configurar
    el scheduler con trigger='cron' si está soportado.
    
    Operaciones:
    - Limpieza de entradas expiradas
    - Logging automático de estadísticas
    
    Args:
        scheduler: Instancia de SchedulerService
    
    Returns:
        ID del job registrado
    """
    job_id = "cache_cleanup_hourly"
    
    # Programar ejecución cada hora
    scheduler.add_interval_job(
        func=cleanup_expired_cache,
        job_id=job_id,
        hours=1,
        minutes=0,
        seconds=0,
    )
    
    logger.info("[cache_cleanup] Job '%s' registered: hourly cleanup", job_id)
    
    return job_id


# Fin del archivo backend/app/shared/scheduler/jobs/cache_cleanup_job.py
