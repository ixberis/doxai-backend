# -*- coding: utf-8 -*-
"""
backend/app/shared/http/request_meta.py

Helpers para extraer metadatos de request (IP, User-Agent) de manera segura
detrás de proxies (Railway, nginx, etc.).

Reutilizable por todos los módulos que necesiten auditoría.

Autor: DoxAI
Fecha: 2025-12-18
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
    En Railway/Heroku/etc., configurar TRUST_PROXY_HEADERS=true.
    """
    return os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("true", "1", "yes")


def get_client_ip(request: Request) -> str:
    """
    Extrae la IP real del cliente de manera segura.
    
    Si TRUST_PROXY_HEADERS=true:
        1. X-Forwarded-For (primer IP, cliente original)
        2. X-Real-IP (patrón nginx)
        3. request.client.host (fallback)
    
    Si TRUST_PROXY_HEADERS=false (default):
        Solo usa request.client.host (IP directa del socket)
    
    Args:
        request: Request de Starlette/FastAPI
    
    Returns:
        IP del cliente como string, o "unknown" si no se puede determinar
    """
    if _trust_proxy_headers():
        # Confiar en headers de proxy
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # X-Forwarded-For: "client, proxy1, proxy2"
            client_ip = xff.split(",")[0].strip()
            return client_ip
        
        # Fallback a X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    
    # Default: IP directa del socket
    if request.client and request.client.host:
        return request.client.host
    
    return "unknown"


def get_user_agent(request: Request) -> Optional[str]:
    """
    Extrae el User-Agent del request.
    
    Args:
        request: Request de Starlette/FastAPI
    
    Returns:
        User-Agent como string, o None si no existe
    """
    ua = request.headers.get("user-agent")
    return ua.strip() if ua else None


def get_request_meta(request: Request) -> dict:
    """
    Extrae metadatos completos del request para auditoría.
    
    Args:
        request: Request de Starlette/FastAPI
    
    Returns:
        Dict con ip_address y user_agent
    """
    return {
        "ip_address": get_client_ip(request),
        "user_agent": get_user_agent(request),
    }


__all__ = [
    "get_client_ip",
    "get_user_agent", 
    "get_request_meta",
]
