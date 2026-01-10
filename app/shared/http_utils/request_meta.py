# -*- coding: utf-8 -*-
"""
backend/app/shared/http_utils/request_meta.py

Helpers para extraer metadatos de request (IP, User-Agent) de manera segura
detrás de proxies (Railway, nginx, etc.).

## Configuración de seguridad

### Variables de entorno

- TRUST_PROXY_HEADERS (default: false)
  Si true, confía en X-Forwarded-For / X-Real-IP para obtener IP real.
  Solo habilitar en entornos detrás de proxy confiable.

- TRUSTED_PROXY_CIDRS (opcional, recomendado si TRUST_PROXY_HEADERS=true)
  Lista de CIDRs separados por coma desde los cuales se confía en headers.
  Ejemplo: "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10"
  
  Si está seteado: solo confía en XFF si request.client.host está en esos CIDRs.
  Si no está seteado: confía en XFF desde cualquier IP (riesgo de spoofing).

### Ejemplo Railway
```bash
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_CIDRS=100.64.0.0/10,10.0.0.0/8
```

Railway usa IPs internas en 100.64.x.x (CGNAT range).

Autor: DoxAI
Fecha: 2025-12-18
"""
from __future__ import annotations

import ipaddress
import os
import logging
from functools import lru_cache
from typing import Optional, List, Tuple

from starlette.requests import Request

from app.shared.utils.log_throttle import log_once_every

logger = logging.getLogger(__name__)

# Environment flag to enable verbose IP security logs (default: off in production)
IP_SECURITY_DEBUG = os.getenv("IP_SECURITY_DEBUG", "0").lower() in ("1", "true", "yes")


# =============================================================================
# Configuración
# =============================================================================

def _trust_proxy_headers() -> bool:
    """
    Verifica si debemos confiar en headers de proxy (X-Forwarded-For).
    
    Default: false (seguro para producción sin proxy configurado).
    En Railway/Heroku/etc., configurar TRUST_PROXY_HEADERS=true.
    """
    return os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("true", "1", "yes")


@lru_cache(maxsize=1)
def _get_trusted_proxy_cidrs() -> Optional[List[ipaddress.IPv4Network | ipaddress.IPv6Network]]:
    """
    Parsea TRUSTED_PROXY_CIDRS en una lista de redes.
    
    Cached para evitar re-parseo en cada request.
    
    Returns:
        Lista de redes, o None si no está configurado
    """
    cidrs_str = os.getenv("TRUSTED_PROXY_CIDRS", "").strip()
    if not cidrs_str:
        return None
    
    networks = []
    for cidr in cidrs_str.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError as e:
            logger.error(f"[IP-CONFIG] Invalid CIDR in TRUSTED_PROXY_CIDRS: {cidr!r} - {e}")
    
    if not networks:
        logger.warning("[IP-CONFIG] TRUSTED_PROXY_CIDRS set but no valid CIDRs parsed")
        return None
    
    logger.info(f"[IP-CONFIG] Loaded {len(networks)} trusted proxy CIDRs")
    return networks


def _is_from_trusted_proxy(client_host: str) -> bool:
    """
    Verifica si client_host pertenece a un CIDR de proxy confiable.
    
    Args:
        client_host: IP del socket directo (request.client.host)
    
    Returns:
        True si está en TRUSTED_PROXY_CIDRS, o si TRUSTED_PROXY_CIDRS no está configurado
    """
    trusted_cidrs = _get_trusted_proxy_cidrs()
    
    # Si no hay CIDRs configurados, confiar en todo (legacy behavior con warning)
    if trusted_cidrs is None:
        return True
    
    if not client_host:
        return False
    
    try:
        client_ip = ipaddress.ip_address(client_host.strip())
    except ValueError:
        return False
    
    for network in trusted_cidrs:
        if client_ip in network:
            return True
    
    return False


# =============================================================================
# Validación de IP
# =============================================================================

def _is_valid_ip(ip_str: str) -> bool:
    """
    Valida que una cadena sea una IP válida (IPv4 o IPv6).
    
    Args:
        ip_str: Cadena a validar
        
    Returns:
        True si es IP válida, False en caso contrario
    """
    if not ip_str:
        return False
    try:
        ipaddress.ip_address(ip_str.strip())
        return True
    except (ValueError, AttributeError):
        return False


def _extract_first_valid_ip_from_xff(xff_header: str) -> Tuple[Optional[str], int, List[str]]:
    """
    Extrae la primera IP válida del header X-Forwarded-For.
    
    El formato estándar es: "client, proxy1, proxy2, ..."
    Tomamos el primer valor válido (cliente original).
    
    Retorna información agregada para logging eficiente (anti log-spam).
    
    Args:
        xff_header: Valor del header X-Forwarded-For
        
    Returns:
        Tuple de (primera_ip_valida, count_invalidas, samples_invalidas)
        - primera_ip_valida: str o None
        - count_invalidas: número de IPs inválidas encontradas
        - samples_invalidas: hasta 3 ejemplos de IPs inválidas
    """
    if not xff_header:
        return None, 0, []
    
    first_valid_ip = None
    invalid_count = 0
    invalid_samples: List[str] = []
    
    for ip_candidate in xff_header.split(","):
        ip_candidate = ip_candidate.strip()
        if not ip_candidate:
            continue
            
        if _is_valid_ip(ip_candidate):
            if first_valid_ip is None:
                first_valid_ip = ip_candidate
            # Seguimos iterando para contar inválidas (si las hay antes)
        else:
            invalid_count += 1
            if len(invalid_samples) < 3:
                # Truncar samples largos para evitar log injection
                sample = ip_candidate[:50] if len(ip_candidate) > 50 else ip_candidate
                invalid_samples.append(repr(sample))
    
    return first_valid_ip, invalid_count, invalid_samples


# =============================================================================
# API Principal
# =============================================================================

def get_client_ip(request: Request) -> str:
    """
    Extrae la IP real del cliente de manera segura.
    
    Comportamiento según configuración:
    
    1. Si TRUST_PROXY_HEADERS=false (default):
       - Solo usa request.client.host (IP directa del socket)
       - Seguro contra spoofing
    
    2. Si TRUST_PROXY_HEADERS=true:
       a. Si TRUSTED_PROXY_CIDRS está configurado:
          - Solo confía en XFF si request.client.host está en esos CIDRs
          - Protección contra spoofing desde IPs no confiables
       b. Si TRUSTED_PROXY_CIDRS no está configurado:
          - Confía en XFF desde cualquier IP (legacy, riesgo documentado)
    
    3. Extracción de XFF (cuando confiamos):
       - Primera IP válida de X-Forwarded-For
       - Fallback a X-Real-IP
       - IPs inválidas se ignoran con 1 warning agregado por request
    
    4. Fallback final:
       - request.client.host validado
       - "unknown" si nada es válido
    
    Args:
        request: Request de Starlette/FastAPI
    
    Returns:
        IP del cliente como string, o "unknown" si no se puede determinar
    """
    # Obtener client.host del socket directo
    socket_host = None
    if request.client and request.client.host:
        socket_host = request.client.host
    
    if _trust_proxy_headers():
        # Verificar si el request viene de un proxy confiable
        if socket_host and not _is_from_trusted_proxy(socket_host):
            # Request NO viene de proxy confiable → ignorar XFF (anti-spoofing)
            # Rate-limited log: max 1 per minute per IP to avoid spam
            if IP_SECURITY_DEBUG:
                log_once_every(
                    f"ip_security_ignored:{socket_host}",
                    60.0,  # 1 minute
                    logger,
                    logging.DEBUG,
                    "[IP-SECURITY] Ignoring proxy headers: %s not in TRUSTED_PROXY_CIDRS",
                    socket_host,
                )
            # Usar socket_host directamente
            if _is_valid_ip(socket_host):
                return socket_host
            return "unknown"
        
        # Confiar en headers de proxy
        
        # 1. X-Forwarded-For (estándar de facto)
        xff = request.headers.get("x-forwarded-for")
        if xff:
            valid_ip, invalid_count, invalid_samples = _extract_first_valid_ip_from_xff(xff)
            
            # Logging agregado: 1 warning máximo por request
            if invalid_count > 0 and valid_ip is None:
                logger.warning(
                    f"[IP-VALIDATION] X-Forwarded-For present but no valid IPs "
                    f"(invalid_count={invalid_count}, samples={invalid_samples})"
                )
            elif invalid_count > 0 and IP_SECURITY_DEBUG:
                logger.debug(
                    "[IP-VALIDATION] X-Forwarded-For had %d invalid entries before valid IP (samples=%s)",
                    invalid_count,
                    invalid_samples,
                )
            
            if valid_ip:
                return valid_ip
        
        # 2. X-Real-IP (patrón nginx)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            real_ip = real_ip.strip()
            if _is_valid_ip(real_ip):
                return real_ip
            else:
                logger.warning(f"[IP-VALIDATION] Invalid X-Real-IP: {real_ip[:50]!r}")
    
    # 3. Fallback: IP directa del socket
    if socket_host:
        if _is_valid_ip(socket_host):
            return socket_host
        # Si request.client.host no es válido, algo muy raro pasa
        logger.error(f"[IP-VALIDATION] Invalid request.client.host: {socket_host[:50]!r}")
    
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


# Para tests: limpiar cache de CIDRs
def _clear_cidr_cache() -> None:
    """Limpia el cache de TRUSTED_PROXY_CIDRS. Solo para tests."""
    _get_trusted_proxy_cidrs.cache_clear()


__all__ = [
    "get_client_ip",
    "get_user_agent", 
    "get_request_meta",
]
