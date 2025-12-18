# -*- coding: utf-8 -*-
"""
backend/app/shared/scheduler/jobs/cache_cleanup_job.py

Job programado para limpieza automática del caché de metadatos.

Ejecuta limpieza cada hora, eliminando entradas expiradas y registrando estadísticas.

Autor: DoxAI
Fecha: 2025-11-05
"""

import logging
from datetime import datetime
from typing import Dict, Any

from app.modules.files.services.cache import get_metadata_cache

logger = logging.getLogger(__name__)


async def cleanup_expired_cache() -> Dict[str, Any]:
    """
    Limpia entradas expiradas del caché de metadatos.
    
    Este job se ejecuta periódicamente para:
    - Eliminar entradas cuyo TTL ha expirado
    - Liberar memoria ocupada por datos obsoletos
    - Registrar estadísticas de limpieza
    
    Returns:
        Dict con estadísticas de la limpieza:
        - timestamp: Momento de ejecución
        - entries_before: Entradas antes de limpieza
        - entries_after: Entradas después de limpieza
        - entries_removed: Cantidad eliminada
        - memory_freed_kb: Memoria aproximada liberada
        - duration_ms: Duración de la limpieza
    """
    start_time = datetime.utcnow()
    logger.info("Iniciando limpieza programada de caché de metadatos")
    
    try:
        cache = get_metadata_cache()
        
        # Estadísticas previas
        stats_before = cache.get_stats()
        entries_before = stats_before['size']
        
        # Ejecutar limpieza
        removed_count = cache.cleanup()
        
        # Estadísticas posteriores
        stats_after = cache.get_stats()
        entries_after = stats_after['size']
        
        # Calcular duración
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        # Estimar memoria liberada (aproximación: 2KB por entrada)
        memory_freed_kb = removed_count * 2
        
        stats = {
            'timestamp': start_time.isoformat(),
            'entries_before': entries_before,
            'entries_after': entries_after,
            'entries_removed': removed_count,
            'memory_freed_kb': memory_freed_kb,
            'duration_ms': round(duration_ms, 2),
            'hit_rate': stats_after['hit_rate_percent'],
            'evictions': stats_after['evictions']
        }
        
        # Log según cantidad eliminada
        if removed_count > 0:
            logger.info(
                f"Limpieza completada: {removed_count} entradas eliminadas, "
                f"~{memory_freed_kb}KB liberados, "
                f"duración: {stats['duration_ms']}ms, "
                f"hit rate: {stats['hit_rate']:.1f}%"
            )
        else:
            logger.debug(
                f"Limpieza completada: sin entradas expiradas, "
                f"duración: {stats['duration_ms']}ms"
            )
        
        # Advertencia si el caché está muy lleno
        if entries_after > cache.max_size * 0.9:
            logger.warning(
                f"Caché al {(entries_after/cache.max_size)*100:.1f}% de capacidad "
                f"({entries_after}/{cache.max_size}). "
                f"Considere aumentar max_size o reducir TTL."
            )
        
        # Advertencia si el hit rate es bajo
        if stats_after['total_requests'] > 100 and stats['hit_rate'] < 60:
            logger.warning(
                f"Hit rate bajo ({stats['hit_rate']:.1f}%). "
                f"El caché podría no estar siendo efectivo. "
                f"Hits: {stats_after['hits']}, Misses: {stats_after['misses']}"
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Error durante limpieza de caché: {e}", exc_info=True)
        return {
            'timestamp': start_time.isoformat(),
            'error': str(e),
            'entries_removed': 0
        }


def register_cache_cleanup_job(scheduler) -> str:
    """
    Registra el job de limpieza de caché en el scheduler.
    
    El job se ejecutará:
    - Cada hora (top of the hour)
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
        hours=1,  # Cada hora
        minutes=0,
        seconds=0
    )
    
    logger.info(
        f"Job '{job_id}' registrado: limpieza de caché cada hora"
    )
    
    return job_id


# Fin del archivo backend/app/shared/scheduler/jobs/cache_cleanup_job.py
