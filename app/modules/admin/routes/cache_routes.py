# -*- coding: utf-8 -*-
"""
backend/app/modules/admin/routes/cache_routes.py

Endpoints administrativos para monitoreo y gestión del caché de metadatos.

Endpoints:
- GET  /admin/cache/stats       - Ver estadísticas del caché
- POST /admin/cache/clear       - Limpiar todo el caché
- POST /admin/cache/invalidate  - Invalidar por patrón
- GET  /admin/cache/health      - Estado del caché

PROTECTED: Requires admin role via require_admin_strict dependency.

Autor: Ixchel Beristain
Fecha: 05/11/2025
Updated: 2026-01-13 (Use require_admin_strict for JWT-based auth)
"""

from typing import Dict
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field, ConfigDict

from app.modules.files.services.cache import get_metadata_cache
from app.modules.auth.dependencies import require_admin_strict
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/cache",
    tags=["Admin - Cache"],
    dependencies=[Depends(require_admin_strict)],  # All routes require admin
)


# ──────────────────────────────────────────────────────────────────────────────
# Modelos de Request/Response
# ──────────────────────────────────────────────────────────────────────────────

class CacheStatsResponse(BaseModel):
    """Estadísticas del caché de metadatos."""
    size: int = Field(..., description="Número de entradas actuales en caché")
    max_size: int = Field(..., description="Capacidad máxima del caché")
    hits: int = Field(..., description="Número de consultas exitosas (cache hit)")
    misses: int = Field(..., description="Número de consultas fallidas (cache miss)")
    hit_rate_percent: float = Field(..., description="Porcentaje de aciertos")
    evictions: int = Field(..., description="Entradas removidas por LRU")
    invalidations: int = Field(..., description="Invalidaciones manuales")
    total_requests: int = Field(..., description="Total de consultas al caché")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "size": 450,
                "max_size": 1000,
                "hits": 2500,
                "misses": 300,
                "hit_rate_percent": 89.29,
                "evictions": 50,
                "invalidations": 20,
                "total_requests": 2800
            }
        }
    )


class InvalidateRequest(BaseModel):
    """Request para invalidar entradas por patrón."""
    pattern: str = Field(
        ...,
        description="Prefijo de las claves a invalidar (ej: 'input_meta:', 'product_meta:')",
        min_length=1
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pattern": "input_meta:"
            }
        }
    )


class InvalidateResponse(BaseModel):
    """Response de invalidación."""
    invalidated_count: int = Field(..., description="Número de entradas invalidadas")
    pattern: str = Field(..., description="Patrón usado")
    message: str = Field(..., description="Mensaje descriptivo")


class ClearResponse(BaseModel):
    """Response de limpieza de caché."""
    cleared_count: int = Field(..., description="Número de entradas eliminadas")
    message: str = Field(..., description="Mensaje descriptivo")


class HealthResponse(BaseModel):
    """Estado de salud del caché."""
    status: str = Field(..., description="Estado del caché (healthy, degraded, critical)")
    size: int = Field(..., description="Entradas actuales")
    capacity_percent: float = Field(..., description="Porcentaje de ocupación")
    hit_rate_percent: float = Field(..., description="Tasa de aciertos")
    warnings: list[str] = Field(default_factory=list, description="Advertencias")


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/stats",
    response_model=CacheStatsResponse,
    summary="Obtener estadísticas del caché",
    description="Retorna estadísticas detalladas del caché de metadatos incluyendo hits, misses, evictions, etc."
)
async def get_cache_stats() -> CacheStatsResponse:
    """
    Obtiene estadísticas actuales del caché de metadatos.
    
    Requires: Bearer token with admin role.
    """
    try:
        cache = get_metadata_cache()
        stats = cache.get_stats()
        
        logger.info(f"Cache stats accessed: hit_rate={stats.get('hit_rate_percent')}%")
        
        return CacheStatsResponse(**stats)
    
    except Exception as e:
        logger.error(f"Error retrieving cache stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving cache stats: {str(e)}"
        )


@router.post(
    "/clear",
    response_model=ClearResponse,
    summary="Limpiar todo el caché",
    description="Elimina todas las entradas del caché. Usar con precaución en producción."
)
async def clear_cache() -> ClearResponse:
    """
    Limpia completamente el caché de metadatos.
    
    **Advertencia**: Esto causará cache misses hasta que se vuelva a llenar.
    
    Requires: Bearer token with admin role.
    """
    try:
        cache = get_metadata_cache()
        
        # Obtener tamaño antes de limpiar
        stats = cache.get_stats()
        size_before = stats["size"]
        
        # Limpiar
        cache.clear()
        
        logger.warning(f"Cache cleared by admin: {size_before} entries removed")
        
        return ClearResponse(
            cleared_count=size_before,
            message=f"Cache cleared successfully. {size_before} entries removed."
        )
    
    except Exception as e:
        logger.error(f"Error clearing cache: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error clearing cache: {str(e)}"
        )


@router.post(
    "/invalidate",
    response_model=InvalidateResponse,
    summary="Invalidar entradas por patrón",
    description="Invalida todas las entradas del caché que coincidan con un prefijo específico."
)
async def invalidate_by_pattern(
    request: InvalidateRequest,
) -> InvalidateResponse:
    """
    Invalida entradas del caché que coincidan con un patrón.
    
    Ejemplos de patrones comunes:
    - `"input_meta:"` - Todos los metadatos de archivos input
    - `"product_meta:"` - Todos los metadatos de archivos product
    - `"input_meta:user123"` - Metadatos de input de un usuario específico
    
    Requires: Bearer token with admin role.
    """
    try:
        cache = get_metadata_cache()
        
        # Invalidar por patrón
        count = cache.invalidate_pattern(request.pattern)
        
        logger.info(
            f"Cache invalidated by admin: pattern='{request.pattern}', "
            f"count={count}"
        )
        
        return InvalidateResponse(
            invalidated_count=count,
            pattern=request.pattern,
            message=f"Invalidated {count} entries matching pattern '{request.pattern}'"
        )
    
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error invalidating cache: {str(e)}"
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Estado de salud del caché",
    description="Evalúa el estado de salud del caché y retorna advertencias si es necesario."
)
async def get_cache_health() -> HealthResponse:
    """
    Evalúa el estado de salud del caché.
    
    Estados:
    - **healthy**: Todo funciona correctamente
    - **degraded**: Hit rate bajo o uso excesivo de memoria
    - **critical**: Problemas graves que requieren atención inmediata
    
    Requires: Bearer token with admin role.
    """
    try:
        cache = get_metadata_cache()
        stats = cache.get_stats()
        
        warnings = []
        status_level = "healthy"
        
        # Calcular métricas
        capacity_percent = (stats["size"] / stats["max_size"] * 100) if stats["max_size"] > 0 else 0
        hit_rate = stats["hit_rate_percent"]
        
        # Evaluar condiciones
        if capacity_percent > 90:
            warnings.append(f"Cache casi lleno ({capacity_percent:.1f}%). Considerar aumentar max_size.")
            status_level = "degraded"
        
        if hit_rate < 50 and stats["total_requests"] > 100:
            warnings.append(f"Hit rate bajo ({hit_rate:.1f}%). Considerar aumentar TTL o revisar patrones de acceso.")
            if status_level == "healthy":
                status_level = "degraded"
        
        if stats["evictions"] > stats["hits"] * 0.5 and stats["evictions"] > 100:
            warnings.append(
                f"Evictions frecuentes ({stats['evictions']}). "
                "Considerar aumentar max_size."
            )
            status_level = "critical"
        
        logger.debug(f"Cache health check: status={status_level}, warnings={len(warnings)}")
        
        return HealthResponse(
            status=status_level,
            size=stats["size"],
            capacity_percent=round(capacity_percent, 2),
            hit_rate_percent=hit_rate,
            warnings=warnings
        )
    
    except Exception as e:
        logger.error(f"Error checking cache health: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking cache health: {str(e)}"
        )


@router.post(
    "/reset-stats",
    summary="Reiniciar estadísticas del caché",
    description="Reinicia los contadores de hits, misses, evictions e invalidations a cero."
)
async def reset_cache_stats() -> Dict[str, str]:
    """
    Reinicia las estadísticas del caché sin afectar las entradas almacenadas.
    
    Útil para medir rendimiento en períodos específicos.
    
    Requires: Bearer token with admin role.
    """
    try:
        cache = get_metadata_cache()
        cache.reset_stats()
        
        logger.info("Cache statistics reset by admin")
        
        return {
            "message": "Cache statistics reset successfully",
            "status": "ok"
        }
    
    except Exception as e:
        logger.error(f"Error resetting cache stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resetting cache stats: {str(e)}"
        )


# Fin del archivo backend/app/modules/admin/routes/cache_routes.py
