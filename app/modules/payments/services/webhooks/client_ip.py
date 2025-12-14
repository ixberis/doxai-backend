# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/webhooks/client_ip.py

BLOQUE B: Extracción segura de IP del cliente para webhooks.

Implementa TRUST_PROXY_HEADERS para entornos con reverse proxy (Railway, etc.).
- TRUST_PROXY_HEADERS=false (default en prod): usa request.client.host
- TRUST_PROXY_HEADERS=true: usa X-Forwarded-For primer IP

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import os
import logging
from typing import Optional

from starlette.requests import Request

logger = logging.getLogger(__name__)


def _trust_proxy_headers() -> bool:
    """
    Verifica si debemos confiar en headers de proxy (X-Forwarded-For).
    
    Default: false (seguro para producción).
    Solo activar si Railway/load balancer está configurado correctamente.
    """
    return os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("true", "1", "yes")


def get_client_ip(request: Request) -> str:
    """
    Extrae la IP real del cliente de manera segura.
    
    Si TRUST_PROXY_HEADERS=true:
        - Usa X-Forwarded-For (primer IP, más cercana al cliente)
        - Fallback a X-Real-IP
        - Fallback a request.client.host
    
    Si TRUST_PROXY_HEADERS=false (default):
        - Solo usa request.client.host (IP directa del socket)
    
    Args:
        request: Request de Starlette/FastAPI
    
    Returns:
        IP del cliente como string, o "unknown" si no se puede determinar
    """
    if _trust_proxy_headers():
        # Confiar en headers de proxy
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # X-Forwarded-For puede ser: "client, proxy1, proxy2"
            # El primer IP es el cliente original
            client_ip = xff.split(",")[0].strip()
            logger.debug(f"Client IP from X-Forwarded-For: {client_ip}")
            return client_ip
        
        # Fallback a X-Real-IP (nginx pattern)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            logger.debug(f"Client IP from X-Real-IP: {real_ip}")
            return real_ip.strip()
    
    # Default: IP directa del socket
    if request.client and request.client.host:
        return request.client.host
    
    logger.warning("No se pudo determinar IP del cliente")
    return "unknown"


def get_client_ip_for_rate_limit(request: Request) -> str:
    """
    Versión específica para rate limiting.
    
    Misma lógica que get_client_ip pero con logging reducido
    para no spamear en alta carga.
    
    Args:
        request: Request de Starlette/FastAPI
    
    Returns:
        IP del cliente como string
    """
    if _trust_proxy_headers():
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    
    if request.client and request.client.host:
        return request.client.host
    
    return "unknown"


__all__ = [
    "get_client_ip",
    "get_client_ip_for_rate_limit",
]
