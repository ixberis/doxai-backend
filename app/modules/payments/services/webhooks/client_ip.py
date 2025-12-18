# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/webhooks/client_ip.py

BLOQUE B: Extracción segura de IP del cliente para webhooks.

NOTA: Este módulo es un wrapper sobre el helper centralizado
app.shared.http_utils.request_meta para mantener compatibilidad
con el código existente de webhooks.

Autor: DoxAI
Fecha: 2025-12-18
"""
from __future__ import annotations

from starlette.requests import Request

# Reutilizar el helper centralizado con validación de IP
from app.shared.http_utils.request_meta import get_client_ip as _get_client_ip_validated


def get_client_ip(request: Request) -> str:
    """
    Extrae la IP real del cliente de manera segura.
    
    Delegado al helper centralizado con validación de IP.
    Ver: app.shared.http_utils.request_meta.get_client_ip
    
    Args:
        request: Request de Starlette/FastAPI
    
    Returns:
        IP del cliente como string, o "unknown" si no se puede determinar
    """
    return _get_client_ip_validated(request)


def get_client_ip_for_rate_limit(request: Request) -> str:
    """
    Versión específica para rate limiting.
    
    Usa la misma lógica validada que get_client_ip.
    El logging del helper centralizado ya es apropiado.
    
    Args:
        request: Request de Starlette/FastAPI
    
    Returns:
        IP del cliente como string
    """
    return _get_client_ip_validated(request)


__all__ = [
    "get_client_ip",
    "get_client_ip_for_rate_limit",
]
