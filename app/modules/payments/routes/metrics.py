# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/routes/metrics.py

Endpoints administrativos para consultar métricas de pagos.

Autor: Ixchel Beristáin
Fecha: 06/11/2025
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

# Dependencias comunes
try:
    from app.modules.auth.services.token_service import get_current_user  # type: ignore
except Exception:  # pragma: no cover
    def get_current_user():  # type: ignore
        raise RuntimeError("get_current_user no disponible")

# Metrics
from app.modules.payments.metrics import (
    get_metrics_collector,
    MetricsCollector,
    EndpointMetrics,
    ProviderConversionMetrics,
    MetricsSnapshot,
    MetricsSummary,
    HealthStatus,
)

router = APIRouter(prefix="/metrics", tags=["payments:metrics"])


def _require_admin(user: Any) -> None:
    """Verifica que el usuario sea administrador."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado"
        )
    
    # Intenta extraer is_admin de diferentes formas
    is_admin = False
    if hasattr(user, "is_admin"):
        is_admin = bool(user.is_admin)
    elif hasattr(user, "role"):
        is_admin = str(user.role).lower() in ["admin", "administrator"]
    elif isinstance(user, dict):
        is_admin = user.get("is_admin", False) or user.get("role", "").lower() in ["admin", "administrator"]
    
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos de administrador requeridos"
        )


def _get_collector() -> MetricsCollector:
    """Dependency para obtener el collector."""
    return get_metrics_collector()


@router.get(
    "/summary",
    response_model=Dict,
    summary="Obtiene un resumen general de métricas",
)
async def get_metrics_summary(
    current_user: Any = Depends(get_current_user),
    collector: MetricsCollector = Depends(_get_collector),
):
    """
    Devuelve un resumen general del sistema de pagos:
    - Uptime del sistema
    - Total de endpoints y proveedores rastreados
    - Métricas agregadas de la última hora
    
    Requiere permisos de administrador.
    """
    _require_admin(current_user)
    
    try:
        summary = collector.get_summary()
        return {
            "success": True,
            "data": summary,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener resumen: {exc.__class__.__name__}",
        )


@router.get(
    "/endpoints",
    response_model=Dict,
    summary="Obtiene métricas de endpoints",
)
async def get_endpoint_metrics(
    endpoint: Optional[str] = Query(None, description="Filtrar por endpoint específico"),
    hours: int = Query(1, ge=1, le=24, description="Ventana de tiempo en horas"),
    current_user: Any = Depends(get_current_user),
    collector: MetricsCollector = Depends(_get_collector),
):
    """
    Devuelve métricas detalladas de endpoints:
    - Total de requests y errores
    - Tasa de error
    - Latencias (P50, P95, P99, promedio)
    - Errores agrupados por tipo
    
    Requiere permisos de administrador.
    """
    _require_admin(current_user)
    
    try:
        metrics = collector.get_endpoint_metrics(endpoint=endpoint, hours=hours)
        
        # Convertir a lista de EndpointMetrics
        endpoint_list = []
        for ep_name, ep_data in metrics.items():
            endpoint_list.append({
                "endpoint": ep_name,
                **ep_data,
            })
        
        return {
            "success": True,
            "time_window_hours": hours,
            "total_endpoints": len(endpoint_list),
            "data": endpoint_list,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener métricas de endpoints: {exc.__class__.__name__}",
        )


@router.get(
    "/conversions",
    response_model=Dict,
    summary="Obtiene tasas de conversión por proveedor",
)
async def get_conversion_metrics(
    provider: Optional[str] = Query(None, description="Filtrar por proveedor específico"),
    hours: int = Query(1, ge=1, le=24, description="Ventana de tiempo en horas"),
    current_user: Any = Depends(get_current_user),
    collector: MetricsCollector = Depends(_get_collector),
):
    """
    Devuelve tasas de conversión por proveedor:
    - Total de intentos
    - Pagos exitosos, fallidos, pendientes, cancelados
    - Tasa de conversión y tasa de fallo
    
    Requiere permisos de administrador.
    """
    _require_admin(current_user)
    
    try:
        conversions = collector.get_provider_conversions(provider=provider, hours=hours)
        
        # Convertir a lista de ProviderConversionMetrics
        provider_list = []
        for prov_name, prov_data in conversions.items():
            provider_list.append({
                "provider": prov_name,
                **prov_data,
            })
        
        return {
            "success": True,
            "time_window_hours": hours,
            "total_providers": len(provider_list),
            "data": provider_list,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener métricas de conversión: {exc.__class__.__name__}",
        )


@router.get(
    "/health",
    response_model=Dict,
    summary="Evalúa el estado de salud del sistema de pagos",
)
async def get_health_status(
    current_user: Any = Depends(get_current_user),
    collector: MetricsCollector = Depends(_get_collector),
):
    """
    Evalúa el estado de salud del sistema y genera alertas:
    - Estado general: healthy, warning, critical
    - Alertas detectadas con nivel y mensaje
    - Resumen de métricas relevantes
    
    Requiere permisos de administrador.
    """
    _require_admin(current_user)
    
    try:
        health = collector.get_health_status()
        return {
            "success": True,
            "data": health,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al evaluar estado de salud: {exc.__class__.__name__}",
        )


@router.get(
    "/snapshot",
    response_model=Dict,
    summary="Obtiene un snapshot completo de todas las métricas",
)
async def get_metrics_snapshot(
    hours: int = Query(1, ge=1, le=24, description="Ventana de tiempo en horas"),
    current_user: Any = Depends(get_current_user),
    collector: MetricsCollector = Depends(_get_collector),
):
    """
    Devuelve un snapshot completo que incluye:
    - Métricas de todos los endpoints
    - Conversiones de todos los proveedores
    - Timestamp del snapshot
    
    Útil para generar reportes o dashboards.
    Requiere permisos de administrador.
    """
    _require_admin(current_user)
    
    try:
        endpoint_metrics = collector.get_endpoint_metrics(hours=hours)
        provider_conversions = collector.get_provider_conversions(hours=hours)
        
        # Formatear endpoints
        endpoints = []
        for ep_name, ep_data in endpoint_metrics.items():
            endpoints.append({
                "endpoint": ep_name,
                **ep_data,
            })
        
        # Formatear proveedores
        providers = []
        for prov_name, prov_data in provider_conversions.items():
            providers.append({
                "provider": prov_name,
                **prov_data,
            })
        
        return {
            "success": True,
            "snapshot": {
                "time_window_hours": hours,
                "endpoints": endpoints,
                "providers": providers,
            }
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar snapshot: {exc.__class__.__name__}",
        )


# Endpoint público para health check básico (sin auth)
@router.get(
    "/ping",
    summary="Health check básico del sistema de métricas",
    include_in_schema=True,
)
async def metrics_ping():
    """
    Health check simple para verificar que el sistema de métricas está activo.
    No requiere autenticación.
    """
    return {
        "status": "ok",
        "service": "payments-metrics",
    }

# Fin del archivo
