# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/webhooks/signature_verification.py

Verificación REAL de firmas para webhooks de Stripe y PayPal.

IMPORTANTE:
- El bypass inseguro SOLO funciona en ENVIRONMENT=development.
- PayPal usa verificación vía API oficial (async, no HMAC local).
- Stripe usa HMAC-SHA256 con el webhook secret.

BLOQUE A (Railway readiness):
- Timeouts explícitos para PayPal: token (connect 5s, read 10s), verify (connect 5s, read 15s)
- Retry limitado (1 intento) solo para errores transitorios (502, 503, 504)
- Cache de token con TTL mantenido

Autor: DoxAI
Fecha: 2025-12-13
"""
from __future__ import annotations

import os
import hmac
import hashlib
import time
import logging
import asyncio
import httpx
from typing import Optional, Dict, Tuple

from app.shared.config.settings_payments import get_payments_settings

logger = logging.getLogger(__name__)


# =============================================================================
# TIMEOUTS CONFIGURABLES (Railway-ready) - A+2
# =============================================================================

# Timeouts para obtener token de PayPal (connect 5s, read 10s, write 10s, pool 5s)
PAYPAL_TOKEN_TIMEOUT = httpx.Timeout(
    connect=float(os.getenv("PAYPAL_TOKEN_CONNECT_TIMEOUT", "5.0")),
    read=float(os.getenv("PAYPAL_TOKEN_READ_TIMEOUT", "10.0")),
    write=float(os.getenv("PAYPAL_TOKEN_WRITE_TIMEOUT", "10.0")),
    pool=5.0,
)

# Timeouts para verificar firma PayPal (connect 5s, read 15s, write 15s, pool 5s)
PAYPAL_VERIFY_TIMEOUT = httpx.Timeout(
    connect=float(os.getenv("PAYPAL_VERIFY_CONNECT_TIMEOUT", "5.0")),
    read=float(os.getenv("PAYPAL_VERIFY_READ_TIMEOUT", "15.0")),
    write=float(os.getenv("PAYPAL_VERIFY_WRITE_TIMEOUT", "15.0")),
    pool=5.0,
)

# Límites de conexión para el cliente HTTP singleton (A+1)
PAYPAL_HTTP_LIMITS = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=50,
    keepalive_expiry=30.0,
)

# Códigos de error HTTP que se consideran transitorios (retry permitido)
# A+3: Incluye 429 (rate limit) como transitorio con backoff mayor
TRANSIENT_HTTP_ERRORS = frozenset({429, 502, 503, 504})

# Máximo de reintentos para errores transitorios
MAX_TRANSIENT_RETRIES = 1

# Backoff base en segundos para reintentos (A+3: mayor para 429)
RETRY_BACKOFF_BASE = 0.5
RETRY_BACKOFF_429 = 2.0  # Backoff mayor para rate limiting


# =============================================================================
# TOKEN CACHE (TTL-based, in-memory)
# 
# NOTA: En Railway con múltiples réplicas, cada réplica tiene su propio cache.
# Para cache distribuido, implementar hook a Redis/Upstash:
#   - Configurar REDIS_URL o UPSTASH_REDIS_URL en ENV
#   - Importar redis async client
#   - Reemplazar _get_cached_token/_set_cached_token por versiones Redis
# Por ahora: cache in-memory es suficiente (cada réplica obtiene su token).
# =============================================================================

_paypal_token_cache: Dict[str, Tuple[str, float]] = {}


def _get_cached_token(cache_key: str) -> Optional[str]:
    """Retorna token si aún es válido, None si expiró o no existe."""
    if cache_key not in _paypal_token_cache:
        return None
    token, expires_at = _paypal_token_cache[cache_key]
    if time.time() >= expires_at:
        del _paypal_token_cache[cache_key]
        return None
    return token


def _set_cached_token(cache_key: str, token: str, expires_in: int) -> None:
    """Cachea token con TTL (expires_in en segundos, restamos 60s de margen)."""
    ttl = max(expires_in - 60, 60)  # Al menos 60s, con 60s de margen
    _paypal_token_cache[cache_key] = (token, time.time() + ttl)


def _clear_token_cache() -> None:
    """Limpia cache de tokens (útil para tests)."""
    _paypal_token_cache.clear()


# =============================================================================
# ENVIRONMENT CHECKS
# =============================================================================

def _is_development_environment() -> bool:
    """
    Verifica si estamos en entorno de desarrollo.
    Solo en desarrollo se permite el bypass de verificación.
    
    NOTA: "test" NO es desarrollo - los tests deben ser fail-closed.
    """
    env = os.getenv("ENVIRONMENT", "production").lower()
    python_env = os.getenv("PYTHON_ENV", "production").lower()
    
    # "test" explícitamente excluido - tests deben verificar firmas
    dev_envs = ("development", "dev", "local")
    return env in dev_envs or python_env in dev_envs


def _allow_insecure() -> bool:
    """
    Determina si se permite el bypass de verificación de firmas.
    
    REGLAS:
    1. La variable PAYMENTS_ALLOW_INSECURE_WEBHOOKS debe ser "true"
    2. ADEMÁS, debe ser entorno de desarrollo (NO test)
    3. PYTHON_ENV != "test" (pytest nunca puede bypass)
    
    En producción y tests, SIEMPRE se requiere verificación real.
    """
    # Fail-closed: tests NUNCA pueden bypass
    python_env = os.getenv("PYTHON_ENV", "production").lower()
    if python_env == "test":
        return False
    
    allow_flag = os.getenv("PAYMENTS_ALLOW_INSECURE_WEBHOOKS", "false").lower() == "true"
    is_dev = _is_development_environment()
    
    if allow_flag and not is_dev:
        logger.error(
            "SECURITY VIOLATION: PAYMENTS_ALLOW_INSECURE_WEBHOOKS=true en entorno "
            "no-desarrollo. Ignorando flag y forzando verificación real."
        )
        return False
    
    if allow_flag and is_dev:
        logger.warning(
            "DESARROLLO: Verificación de webhooks deshabilitada. "
            "Esto NUNCA debe ocurrir en producción."
        )
        return True
    
    return False


def _is_transient_error(status_code: int) -> bool:
    """Verifica si un código HTTP es un error transitorio (permite retry)."""
    return status_code in TRANSIENT_HTTP_ERRORS


def _get_backoff_for_status(status_code: int, attempt: int) -> float:
    """Calcula backoff según tipo de error (A+3: 429 usa backoff mayor)."""
    if status_code == 429:
        return RETRY_BACKOFF_429 * (2 ** attempt)
    return RETRY_BACKOFF_BASE * (2 ** attempt)


# =============================================================================
# SINGLETON HTTP CLIENT (A+1: Keep-alive, connection pooling)
# 
# NOTA: El cliente singleton mantiene conexiones keep-alive para Railway.
# NO usar "async with" por request; el cliente se reutiliza.
# Para cleanup en shutdown, registrar close_paypal_http_clients() en lifespan.
# =============================================================================

# Claves explícitas para clientes (evita problemas con repr de timeout)
PAYPAL_CLIENT_TOKEN = "paypal_token"
PAYPAL_CLIENT_VERIFY = "paypal_verify"

_paypal_clients: Dict[str, httpx.AsyncClient] = {}

# HTTP/2 configurable por ENV (default: false para evitar edge-cases con proxies)
_use_http2 = os.getenv("PAYPAL_HTTP2_ENABLED", "false").lower() in ("true", "1", "yes")


def get_paypal_http_client_by_key(client_key: str, timeout: httpx.Timeout) -> httpx.AsyncClient:
    """
    Retorna cliente HTTP singleton para PayPal con keep-alive.
    
    Usa claves explícitas para identificar el cliente (token vs verify).
    Reutiliza conexiones para evitar overhead de handshake TLS.
    
    Args:
        client_key: Clave del cliente (PAYPAL_CLIENT_TOKEN o PAYPAL_CLIENT_VERIFY)
        timeout: Configuración de timeout
    
    Returns:
        httpx.AsyncClient configurado y reutilizable
    """
    if client_key not in _paypal_clients:
        _paypal_clients[client_key] = httpx.AsyncClient(
            timeout=timeout,
            limits=PAYPAL_HTTP_LIMITS,
            http2=_use_http2,
        )
        logger.debug(f"Creado cliente PayPal HTTP singleton (key={client_key}, http2={_use_http2})")
    
    return _paypal_clients[client_key]


def get_paypal_token_client() -> httpx.AsyncClient:
    """Cliente singleton para obtener token de PayPal."""
    return get_paypal_http_client_by_key(PAYPAL_CLIENT_TOKEN, PAYPAL_TOKEN_TIMEOUT)


def get_paypal_verify_client() -> httpx.AsyncClient:
    """Cliente singleton para verificar firma de PayPal."""
    return get_paypal_http_client_by_key(PAYPAL_CLIENT_VERIFY, PAYPAL_VERIFY_TIMEOUT)


async def close_paypal_http_clients() -> None:
    """
    Cierra todos los clientes HTTP de PayPal.
    Registrar en FastAPI lifespan para cleanup en shutdown.
    
    Ejemplo de uso con lifespan:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            yield
            await close_paypal_http_clients()
    """
    for key, client in list(_paypal_clients.items()):
        try:
            await client.aclose()
            logger.debug(f"Cliente PayPal HTTP cerrado (key={key})")
        except Exception as e:
            logger.warning(f"Error cerrando cliente PayPal HTTP: {e}")
    _paypal_clients.clear()


def _reset_paypal_clients() -> None:
    """Reset clientes para tests (sync, no cierra)."""
    _paypal_clients.clear()


def _get_paypal_clients_count() -> int:
    """Retorna número de clientes activos (para tests)."""
    return len(_paypal_clients)


# =============================================================================
# STRIPE VERIFICATION
# =============================================================================

def verify_stripe_signature(
    payload: bytes,
    signature_header: Optional[str],
    webhook_secret: Optional[str] = None,
    tolerance_seconds: int = 300,
) -> bool:
    """
    Verifica la firma de un webhook de Stripe usando HMAC-SHA256.
    
    Args:
        payload: Body crudo del request
        signature_header: Header Stripe-Signature
        webhook_secret: Secret del webhook (whsec_...)
        tolerance_seconds: Tolerancia de timestamp (default 5 minutos)
    
    Returns:
        True si la firma es válida, False en caso contrario
    """
    # Bypass solo en desarrollo
    if _allow_insecure():
        return True
    
    # Obtener secret de settings si no se proporciona
    if webhook_secret is None:
        settings = get_payments_settings()
        webhook_secret = settings.stripe_webhook_secret
    
    # Validaciones obligatorias
    if not signature_header:
        logger.warning("Stripe webhook rechazado: falta header Stripe-Signature")
        return False
    
    if not webhook_secret:
        logger.error(
            "Stripe webhook rechazado: STRIPE_WEBHOOK_SECRET no configurado."
        )
        return False
    
    try:
        # Parsear header: "t=timestamp,v1=signature,v0=signature_old"
        elements: Dict[str, list] = {}
        for item in signature_header.split(","):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                elements.setdefault(key, []).append(value)
        
        timestamp_str = elements.get("t", [None])[0]
        signatures_v1 = elements.get("v1", [])
        
        if not timestamp_str:
            logger.warning("Stripe webhook rechazado: timestamp no encontrado en header")
            return False
        
        if not signatures_v1:
            logger.warning("Stripe webhook rechazado: firma v1 no encontrada en header")
            return False
        
        # Verificar tolerancia de timestamp
        timestamp = int(timestamp_str)
        now = int(time.time())
        
        if abs(now - timestamp) > tolerance_seconds:
            logger.warning(
                f"Stripe webhook rechazado: timestamp fuera de tolerancia. "
                f"Diferencia: {abs(now - timestamp)}s, tolerancia: {tolerance_seconds}s"
            )
            return False
        
        # Calcular firma esperada
        signed_payload = f"{timestamp}.".encode("utf-8") + payload
        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"),
            msg=signed_payload,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Verificar contra cualquiera de las firmas v1
        for sig in signatures_v1:
            if hmac.compare_digest(expected_signature, sig):
                logger.debug("Stripe webhook: firma verificada correctamente")
                return True
        
        logger.warning("Stripe webhook rechazado: ninguna firma v1 coincide")
        return False
        
    except ValueError as e:
        logger.warning(f"Stripe webhook rechazado: error parseando timestamp - {e}")
        return False
    except Exception as e:
        logger.error(f"Stripe webhook rechazado: error inesperado - {e}")
        return False


# =============================================================================
# PAYPAL VERIFICATION - VÍA API OFICIAL (ASYNC)
# =============================================================================

async def _get_paypal_access_token_async(
    client_id: str,
    client_secret: str,
    is_sandbox: bool = True,
) -> Optional[str]:
    """
    Obtiene un access token de PayPal para llamadas a la API (async).
    Cachea el token basado en expires_in.
    
    BLOQUE A: Timeouts explícitos y retry limitado para Railway.
    
    Args:
        client_id: PayPal Client ID
        client_secret: PayPal Client Secret
        is_sandbox: True para sandbox, False para producción
    
    Returns:
        Access token o None si falla
    """
    cache_key = f"{client_id}:{is_sandbox}"
    
    # Intentar cache primero
    cached = _get_cached_token(cache_key)
    if cached:
        logger.debug("PayPal access token obtenido de cache")
        return cached
    
    base_url = "https://api-m.sandbox.paypal.com" if is_sandbox else "https://api-m.paypal.com"
    token_url = f"{base_url}/v1/oauth2/token"
    
    last_error: Optional[Exception] = None
    
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            # A+1: Usar cliente singleton con keep-alive
            client = get_paypal_token_client()
            response = await client.post(
                token_url,
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json"},
            )
            
            # A+3: Si es error transitorio y quedan reintentos, usar backoff apropiado
            if _is_transient_error(response.status_code) and attempt < MAX_TRANSIENT_RETRIES:
                backoff = _get_backoff_for_status(response.status_code, attempt)
                logger.warning(
                    f"PayPal token request: error transitorio {response.status_code}, "
                    f"reintentando en {backoff}s (intento {attempt + 1}/{MAX_TRANSIENT_RETRIES + 1})"
                )
                await asyncio.sleep(backoff)
                continue
            
            if response.status_code != 200:
                logger.error(
                    f"PayPal token request failed: {response.status_code} - {response.text[:200]}"
                )
                return None
            
            data = response.json()
            access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            
            if access_token:
                _set_cached_token(cache_key, access_token, expires_in)
                logger.debug(f"PayPal access token obtenido y cacheado (TTL={expires_in}s)")
            
            return access_token
            
        except httpx.TimeoutException as e:
            last_error = e
            if attempt < MAX_TRANSIENT_RETRIES:
                backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    f"PayPal token request timeout, reintentando en {backoff}s "
                    f"(intento {attempt + 1}/{MAX_TRANSIENT_RETRIES + 1})"
                )
                await asyncio.sleep(backoff)
                continue
            break
        except Exception as e:
            # Otros errores no son transitorios, no reintentar
            logger.error(f"Error obteniendo PayPal access token: {e}")
            return None
    
    logger.error(f"PayPal token request falló después de {MAX_TRANSIENT_RETRIES + 1} intentos: {last_error}")
    return None


async def verify_paypal_signature_via_api(
    payload: bytes,
    transmission_id: Optional[str],
    transmission_sig: Optional[str],
    cert_url: Optional[str],
    transmission_time: Optional[str],
    auth_algo: Optional[str],
    webhook_id: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    is_sandbox: bool = True,
) -> bool:
    """
    Verifica la firma de un webhook de PayPal usando la API oficial (async).
    
    BLOQUE A: Timeouts explícitos y retry limitado para errores transitorios.
    
    Llama al endpoint POST /v1/notifications/verify-webhook-signature
    
    Args:
        payload: Body crudo del request (JSON del evento)
        transmission_id: Header PAYPAL-TRANSMISSION-ID
        transmission_sig: Header PAYPAL-TRANSMISSION-SIG
        cert_url: Header PAYPAL-CERT-URL (REQUERIDO)
        transmission_time: Header PAYPAL-TRANSMISSION-TIME
        auth_algo: Header PAYPAL-AUTH-ALGO (REQUERIDO)
        webhook_id: ID del webhook configurado en PayPal
        client_id: PayPal Client ID
        client_secret: PayPal Client Secret
        is_sandbox: True para sandbox, False para producción
    
    Returns:
        True solo si PayPal responde verification_status == "SUCCESS"
    """
    # Validar headers requeridos (fail-closed: cualquier faltante = False)
    required_headers = {
        "transmission_id": transmission_id,
        "transmission_sig": transmission_sig,
        "transmission_time": transmission_time,
        "cert_url": cert_url,
        "auth_algo": auth_algo,
    }
    
    missing = [name for name, value in required_headers.items() if not value]
    if missing:
        logger.warning(f"PayPal webhook rechazado: faltan headers requeridos {missing}")
        return False
    
    if not webhook_id:
        logger.error("PayPal webhook rechazado: webhook_id no configurado")
        return False
    
    if not client_id or not client_secret:
        logger.error("PayPal webhook rechazado: client_id o client_secret no configurados")
        return False
    
    # Obtener access token (async con cache)
    access_token = await _get_paypal_access_token_async(client_id, client_secret, is_sandbox)
    if not access_token:
        logger.error("PayPal webhook rechazado: no se pudo obtener access token")
        return False
    
    # Preparar request de verificación
    base_url = "https://api-m.sandbox.paypal.com" if is_sandbox else "https://api-m.paypal.com"
    verify_url = f"{base_url}/v1/notifications/verify-webhook-signature"
    
    try:
        # Parsear el webhook event del payload
        import json
        webhook_event = json.loads(payload.decode("utf-8"))
    except Exception as e:
        logger.error(f"PayPal webhook rechazado: payload no es JSON válido - {e}")
        return False
    
    verification_payload = {
        "auth_algo": auth_algo,
        "cert_url": cert_url,
        "transmission_id": transmission_id,
        "transmission_sig": transmission_sig,
        "transmission_time": transmission_time,
        "webhook_id": webhook_id,
        "webhook_event": webhook_event,
    }
    
    last_error: Optional[Exception] = None
    
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            # A+1: Usar cliente singleton con keep-alive
            client = get_paypal_verify_client()
            response = await client.post(
                verify_url,
                json=verification_payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            
            # A+3: Si es error transitorio y quedan reintentos, usar backoff apropiado
            if _is_transient_error(response.status_code) and attempt < MAX_TRANSIENT_RETRIES:
                backoff = _get_backoff_for_status(response.status_code, attempt)
                logger.warning(
                    f"PayPal verify request: error transitorio {response.status_code}, "
                    f"reintentando en {backoff}s (intento {attempt + 1}/{MAX_TRANSIENT_RETRIES + 1})"
                )
                await asyncio.sleep(backoff)
                continue
            
            if response.status_code != 200:
                logger.warning(
                    f"PayPal verify-webhook-signature failed: "
                    f"{response.status_code} - {response.text[:200]}"
                )
                return False
            
            data = response.json()
            verification_status = data.get("verification_status", "")
            
            if verification_status == "SUCCESS":
                logger.debug("PayPal webhook: firma verificada via API")
                return True
            else:
                logger.warning(
                    f"PayPal webhook rechazado: verification_status = {verification_status}"
                )
                return False
                
        except httpx.TimeoutException as e:
            last_error = e
            if attempt < MAX_TRANSIENT_RETRIES:
                backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    f"PayPal verify request timeout, reintentando en {backoff}s "
                    f"(intento {attempt + 1}/{MAX_TRANSIENT_RETRIES + 1})"
                )
                await asyncio.sleep(backoff)
                continue
            break
        except Exception as e:
            logger.error(f"PayPal webhook rechazado: error llamando a verify API - {e}")
            return False
    
    logger.error(f"PayPal verify request falló después de {MAX_TRANSIENT_RETRIES + 1} intentos: {last_error}")
    return False


async def verify_paypal_signature(
    payload: bytes,
    transmission_id: Optional[str],
    transmission_sig: Optional[str],
    cert_url: Optional[str],
    transmission_time: Optional[str],
    webhook_id: Optional[str] = None,
    auth_algo: Optional[str] = None,
) -> bool:
    """
    Verifica la firma de un webhook de PayPal (async).
    
    Usa la API oficial de PayPal para verificación (no HMAC local).
    
    Args:
        payload: Body crudo del request
        transmission_id: Header PAYPAL-TRANSMISSION-ID
        transmission_sig: Header PAYPAL-TRANSMISSION-SIG
        cert_url: Header PAYPAL-CERT-URL
        transmission_time: Header PAYPAL-TRANSMISSION-TIME
        webhook_id: ID del webhook en PayPal
        auth_algo: Header PAYPAL-AUTH-ALGO
    
    Returns:
        True si la firma es válida (verificada por PayPal API)
    """
    # Bypass solo en desarrollo
    if _allow_insecure():
        return True
    
    # Obtener configuración
    settings = get_payments_settings()
    
    if webhook_id is None:
        webhook_id = settings.paypal_webhook_id
    
    client_id = settings.paypal_client_id
    client_secret = settings.paypal_client_secret
    is_sandbox = settings.paypal_mode == "sandbox"
    
    return await verify_paypal_signature_via_api(
        payload=payload,
        transmission_id=transmission_id,
        transmission_sig=transmission_sig,
        cert_url=cert_url,
        transmission_time=transmission_time,
        auth_algo=auth_algo,
        webhook_id=webhook_id,
        client_id=client_id,
        client_secret=client_secret,
        is_sandbox=is_sandbox,
    )


# Alias para compatibilidad
def verify_stripe_webhook_signature(*args, **kwargs) -> bool:
    return verify_stripe_signature(*args, **kwargs)


async def verify_paypal_webhook_signature(*args, **kwargs) -> bool:
    return await verify_paypal_signature(*args, **kwargs)


__all__ = [
    "verify_stripe_signature",
    "verify_paypal_signature",
    "verify_paypal_signature_via_api",
    "verify_stripe_webhook_signature",
    "verify_paypal_webhook_signature",
    "_is_development_environment",
    "_allow_insecure",
    "_is_transient_error",
    "_get_paypal_access_token_async",
    "_clear_token_cache",
    # Constantes de configuración (BLOQUE A)
    "PAYPAL_TOKEN_TIMEOUT",
    "PAYPAL_VERIFY_TIMEOUT",
    "TRANSIENT_HTTP_ERRORS",
    "MAX_TRANSIENT_RETRIES",
    "RETRY_BACKOFF_BASE",
]

# Fin del archivo backend/app/modules/payments/services/webhooks/signature_verification.py
