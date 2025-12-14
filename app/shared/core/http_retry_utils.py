# -*- coding: utf-8 -*-
"""
backend/app/shared/core/http_retry_utils.py

Utilidades para reintentos con backoff exponencial en llamadas HTTP críticas.
Wrapper opcional para políticas avanzadas de retry que van más allá del
transporte básico (retries=2).

Uso:
    from app.shared.core import get_http_client, retry_with_backoff
    
    client = await get_http_client()
    response = await retry_with_backoff(
        client.get,
        "https://api.example.com/critical",
        max_retries=3,
        base_delay=1.0
    )

Autor: Ixchel Beristain
Fecha: 24/10/2025
"""

from __future__ import annotations
import asyncio
import logging
import random
from typing import Callable, Any, Optional

import httpx

logger = logging.getLogger(__name__)


async def retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retry_on_status: Optional[set[int]] = None,
    auto_raise: bool = False,
    **kwargs
) -> Any:
    """
    Ejecuta una función HTTP con reintentos y backoff exponencial.
    
    Args:
        func: Función async a ejecutar (ej: client.get, client.post)
        *args: Argumentos posicionales para func
        max_retries: Número máximo de reintentos
        base_delay: Delay inicial en segundos
        max_delay: Delay máximo en segundos
        backoff_factor: Factor de multiplicación del delay
        retry_on_status: Set de códigos HTTP que deben reintentarse (default: 5xx)
        auto_raise: Si True, llama raise_for_status() en respuestas exitosas
        **kwargs: Argumentos nombrados para func
        
    Returns:
        Response de httpx si tiene éxito
        
    Raises:
        httpx.HTTPError: Si todos los reintentos fallan
    """
    # Validaciones de entrada
    if max_retries < 0:
        raise ValueError(f"max_retries debe ser >= 0, recibido: {max_retries}")
    if base_delay <= 0:
        raise ValueError(f"base_delay debe ser > 0, recibido: {base_delay}")
    
    if retry_on_status is None:
        retry_on_status = {429, 500, 502, 503, 504}
    
    last_exception = None
    delay = base_delay
    
    for attempt in range(max_retries + 1):
        try:
            response = await func(*args, **kwargs)
            
            # Verificar si el código de estado requiere reintento
            if response.status_code in retry_on_status:
                if attempt < max_retries:
                    logger.warning(
                        f"HTTP {response.status_code} en intento {attempt + 1}/{max_retries + 1}, "
                        f"reintentando en {delay:.1f}s..."
                    )
                    # Añadir jitter para evitar thundering herd
                    jittered_delay = delay + random.uniform(0, 0.2 * delay)
                    await asyncio.sleep(jittered_delay)
                    delay = min(delay * backoff_factor, max_delay)
                    continue
                else:
                    logger.error(f"HTTP {response.status_code} tras {max_retries + 1} intentos")
                    response.raise_for_status()
            
            # Respuesta exitosa
            if attempt > 0:
                logger.info(f"✅ Éxito tras {attempt + 1} intentos")
            
            # Opcionalmente forzar raise_for_status en endpoints críticos
            if auto_raise:
                response.raise_for_status()
            
            return response
            
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(
                    f"Error de transporte ({type(e).__name__}) en intento {attempt + 1}/{max_retries + 1}, "
                    f"reintentando en {delay:.1f}s..."
                )
                # Añadir jitter para evitar thundering herd
                jittered_delay = delay + random.uniform(0, 0.2 * delay)
                await asyncio.sleep(jittered_delay)
                delay = min(delay * backoff_factor, max_delay)
            else:
                logger.error(f"❌ Error de transporte tras {max_retries + 1} intentos: {e}")
                raise
        except httpx.HTTPStatusError as e:
            # Error HTTP que no está en retry_on_status
            logger.error(f"❌ Error HTTP {e.response.status_code}: {e}")
            raise
    
    # Si llegamos aquí, agotamos reintentos
    if last_exception:
        raise last_exception
    raise RuntimeError("Reintentos agotados sin excepción clara")


async def retry_get_with_backoff(
    url: str,
    client: httpx.AsyncClient,
    max_retries: int = 3,
    **kwargs
) -> httpx.Response:
    """
    Shortcut para GET con reintentos y backoff.
    
    Ejemplo:
        client = await get_http_client()
        response = await retry_get_with_backoff(
            "https://api.example.com/data",
            client,
            max_retries=3,
            params={"id": 123}
        )
    """
    return await retry_with_backoff(
        client.get,
        url,
        max_retries=max_retries,
        **kwargs
    )


async def retry_post_with_backoff(
    url: str,
    client: httpx.AsyncClient,
    max_retries: int = 3,
    **kwargs
) -> httpx.Response:
    """
    Shortcut para POST con reintentos y backoff.
    
    Ejemplo:
        client = await get_http_client()
        response = await retry_post_with_backoff(
            "https://api.example.com/process",
            client,
            max_retries=3,
            json={"data": "value"}
        )
    """
    return await retry_with_backoff(
        client.post,
        url,
        max_retries=max_retries,
        **kwargs
    )


# Fin del archivo backend/app/shared/core/http_retry_utils.py
