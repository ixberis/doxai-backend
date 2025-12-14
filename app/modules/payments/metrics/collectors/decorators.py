
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/collectors/decorators.py

Decorators para captura automática de métricas en endpoints.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

import functools
import logging
import time
import inspect
from typing import Callable, Optional, Any

from fastapi import Request, Response

from ..collectors.metrics_collector import get_metrics_collector

logger = logging.getLogger(__name__)


def track_endpoint_metrics(endpoint_name: Optional[str] = None):
    """
    Decorator para capturar métricas de un endpoint automáticamente.

    Captura:
    - Latencia de la llamada
    - Código de estado HTTP
    - Errores y excepciones

    Uso:
        @router.post("/checkout")
        @track_endpoint_metrics("POST /payments/checkout")
        async def checkout_endpoint(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Determinar nombre del endpoint
            ep_name = endpoint_name or f"{func.__module__}.{func.__name__}"

            # Extraer request si está disponible
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get("request")

            # Medir latencia
            start_time = time.time()
            status_code = 200
            error_type = None

            try:
                result = await func(*args, **kwargs)

                # Intentar extraer status code de la respuesta
                if isinstance(result, Response):
                    status_code = result.status_code
                elif isinstance(result, dict) and "status_code" in result:
                    status_code = result["status_code"]

                return result

            except Exception as exc:
                # Registrar el tipo de error
                error_type = exc.__class__.__name__

                # Intentar determinar status code del error
                if hasattr(exc, "status_code"):
                    status_code = exc.status_code
                else:
                    status_code = 500

                # Re-lanzar la excepción para que FastAPI la maneje
                raise

            finally:
                # Calcular latencia
                latency_ms = (time.time() - start_time) * 1000

                # Registrar métricas
                collector = get_metrics_collector()
                collector.record_endpoint_call(
                    endpoint=ep_name,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error=error_type,
                )

                # Log adicional para debugging
                logger.debug(
                    f"Metrics: {ep_name} | {latency_ms:.2f}ms | "
                    f"status={status_code} | error={error_type}"
                )

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Versión síncrona (por si acaso)
            ep_name = endpoint_name or f"{func.__module__}.{func.__name__}"
            start_time = time.time()
            status_code = 200
            error_type = None

            try:
                result = func(*args, **kwargs)

                if isinstance(result, Response):
                    status_code = result.status_code
                elif isinstance(result, dict) and "status_code" in result:
                    status_code = result["status_code"]

                return result

            except Exception as exc:
                error_type = exc.__class__.__name__
                status_code = getattr(exc, "status_code", 500)
                raise

            finally:
                latency_ms = (time.time() - start_time) * 1000
                collector = get_metrics_collector()
                collector.record_endpoint_call(
                    endpoint=ep_name,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error=error_type,
                )

        # Retornar wrapper apropiado
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def track_payment_conversion(provider_param: str = "provider"):
    """
    Decorator para rastrear conversiones de pago.

    Captura intentos de pago y su resultado para calcular tasas de conversión.

    Args:
        provider_param: Nombre del parámetro que contiene el proveedor

    Uso:
        @router.post("/checkout")
        @track_payment_conversion(provider_param="provider")
        async def checkout_endpoint(provider: str, ...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            provider = kwargs.get(provider_param, "unknown")
            status = "unknown"

            try:
                result = await func(*args, **kwargs)

                # Intentar extraer el status del resultado
                if isinstance(result, dict):
                    status = result.get("status") or result.get("payment_status", "succeeded")
                else:
                    status = "succeeded"

                return result

            except Exception:
                status = "failed"
                raise

            finally:
                # Registrar intento de conversión
                collector = get_metrics_collector()
                collector.record_payment_attempt(
                    provider=str(provider),
                    status=status,
                )

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            provider = kwargs.get(provider_param, "unknown")
            status = "unknown"

            try:
                result = func(*args, **kwargs)

                if isinstance(result, dict):
                    status = result.get("status") or result.get("payment_status", "succeeded")
                else:
                    status = "succeeded"

                return result

            except Exception:
                status = "failed"
                raise

            finally:
                collector = get_metrics_collector()
                collector.record_payment_attempt(
                    provider=str(provider),
                    status=status,
                )

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def track_method_metrics(method_name: Optional[str] = None):
    """
    Decorator genérico para métodos de servicio.
    Similar a track_endpoint_metrics pero para servicios internos.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            name = method_name or f"{func.__module__}.{func.__qualname__}"
            start_time = time.time()
            error_type = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as exc:
                error_type = exc.__class__.__name__
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000
                collector = get_metrics_collector()
                collector.record_endpoint_call(
                    endpoint=f"SERVICE:{name}",
                    latency_ms=latency_ms,
                    status_code=500 if error_type else 200,
                    error=error_type,
                )

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return func  # No decorar funciones síncronas por ahora

    return decorator
# Fin del archivo backend\app\modules\payments\metrics\collectors\decorators.py
