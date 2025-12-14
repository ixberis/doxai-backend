
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/services/webhooks/payload_sanitizer.py

BLOQUE D+: Persistencia segura de payloads (whitelist + hash + core fields, cero PII).

En lugar de sanitizar por blacklist (puede escapar PII), usamos:
- WHITELIST estricta: solo campos explícitamente permitidos
- CORE FIELDS: campos mínimos por provider (independiente de whitelist)
- HASH del payload original para trazabilidad
- Nunca se guarda el payload completo

Autor: DoxAI
Fecha: 2025-12-13
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# WHITELIST DE CAMPOS DE AUDITORÍA (BLOQUE D)
#
# Solo estos campos se persisten. Todo lo demás se descarta.
# =============================================================================

AUDIT_FIELDS_WHITELIST: Set[str] = {
    # IDs de eventos y transacciones
    "id",
    "event_id",
    "object",
    "type",
    "event_type",
    
    # IDs de pago (sin PII)
    "payment_intent",
    "payment_intent_id",
    "session_id",
    "checkout_session",
    "charge",
    "charge_id",
    "invoice",
    "invoice_id",
    "subscription",
    "subscription_id",
    "order_id",
    "capture_id",
    "authorization_id",
    "refund_id",
    
    # Montos y moneda (necesarios para auditoría)
    "amount",
    "amount_total",
    "amount_subtotal",
    "amount_received",
    "amount_captured",
    "amount_refunded",
    "currency",
    "unit_amount",
    "total",
    
    # Estados
    "status",
    "payment_status",
    "state",
    "outcome",
    "result",
    
    # Timestamps
    "created",
    "created_at",
    "updated_at",
    "paid_at",
    "captured_at",
    
    # Metadatos técnicos (sin PII)
    "livemode",
    "mode",
    "api_version",
    "resource_type",
}


# =============================================================================
# D+ HARDENING: CORE FIELDS POR PROVIDER
#
# Campos mínimos que SIEMPRE se extraen si existen, independiente de whitelist.
# Estos son esenciales para auditoría y reconciliación.
# =============================================================================

CORE_FIELD_MAPPINGS = {
    "stripe": {
        "core.event_id": ["id"],
        "core.event_type": ["type"],
        "core.provider_payment_id": ["data.object.payment_intent", "data.object.id"],
        "core.provider_session_id": ["data.object.id", "data.object.session_id"],
        "core.amount": ["data.object.amount", "data.object.amount_total"],
        "core.currency": ["data.object.currency"],
        "core.status": ["data.object.status", "data.object.payment_status"],
        "core.livemode": ["livemode"],
    },
    "paypal": {
        "core.event_id": ["id"],
        "core.event_type": ["event_type"],
        "core.provider_payment_id": ["resource.id", "resource.supplementary_data.related_ids.order_id"],
        "core.provider_session_id": ["resource.id"],
        "core.amount": ["resource.amount.value", "resource.purchase_units.0.amount.value"],
        "core.currency": ["resource.amount.currency_code", "resource.purchase_units.0.amount.currency_code"],
        "core.status": ["resource.status", "resource.state"],
        "core.livemode": [],  # PayPal no tiene livemode directo
    },
}


def compute_payload_hash(raw_payload: bytes | str | dict) -> str:
    """
    Calcula SHA256 del payload original para trazabilidad.
    
    Args:
        raw_payload: Payload en bytes, string o dict
    
    Returns:
        Hash SHA256 del payload
    """
    if isinstance(raw_payload, dict):
        payload_bytes = json.dumps(raw_payload, sort_keys=True).encode("utf-8")
    elif isinstance(raw_payload, str):
        payload_bytes = raw_payload.encode("utf-8")
    else:
        payload_bytes = raw_payload
    
    return hashlib.sha256(payload_bytes).hexdigest()


def _get_nested_value(data: Dict[str, Any], path: str) -> Optional[Any]:
    """
    Obtiene valor anidado usando notación de punto.
    
    Args:
        data: Diccionario fuente
        path: Path como "data.object.amount"
    
    Returns:
        Valor encontrado o None
    """
    keys = path.split(".")
    current = data
    
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            try:
                idx = int(key)
                current = current[idx] if idx < len(current) else None
            except (ValueError, IndexError):
                return None
        else:
            return None
        
        if current is None:
            return None
    
    return current


def _extract_core_fields(provider: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    D+ HARDENING: Extrae campos core mínimos para auditoría.
    
    Estos campos se extraen SIEMPRE si existen, independiente de whitelist.
    Son esenciales para reconciliación y auditoría.
    
    Args:
        provider: Nombre del proveedor (stripe/paypal)
        payload: Payload completo del webhook
    
    Returns:
        Dict con campos core.* extraídos
    """
    provider_lower = provider.lower()
    mappings = CORE_FIELD_MAPPINGS.get(provider_lower, CORE_FIELD_MAPPINGS["stripe"])
    
    core_fields = {}
    
    for core_key, source_paths in mappings.items():
        for path in source_paths:
            value = _get_nested_value(payload, path)
            if value is not None:
                core_fields[core_key] = value
                break  # Usar el primer valor encontrado
    
    return core_fields


def _extract_whitelisted_fields(
    data: Dict[str, Any],
    depth: int = 0,
    max_depth: int = 5,
) -> Dict[str, Any]:
    """
    Extrae solo campos en la whitelist de un diccionario.
    
    Args:
        data: Diccionario a procesar
        depth: Profundidad actual
        max_depth: Profundidad máxima
    
    Returns:
        Diccionario con solo campos permitidos
    """
    if depth > max_depth:
        return {}
    
    extracted = {}
    
    for key, value in data.items():
        key_lower = key.lower()
        
        if key_lower in AUDIT_FIELDS_WHITELIST:
            # Campo permitido: incluirlo
            if isinstance(value, dict):
                # Para dicts anidados, extraer recursivamente
                nested = _extract_whitelisted_fields(value, depth + 1, max_depth)
                if nested:  # Solo incluir si tiene contenido
                    extracted[key] = nested
            elif isinstance(value, list):
                # Para listas, procesar cada elemento
                processed_list = []
                for item in value:
                    if isinstance(item, dict):
                        nested = _extract_whitelisted_fields(item, depth + 1, max_depth)
                        if nested:
                            processed_list.append(nested)
                    else:
                        processed_list.append(item)
                if processed_list:
                    extracted[key] = processed_list
            else:
                # Valor primitivo
                extracted[key] = value
        
        elif isinstance(value, dict):
            # Campo no permitido pero es dict: buscar campos permitidos dentro
            nested = _extract_whitelisted_fields(value, depth + 1, max_depth)
            if nested:
                # Prefijamos con el nombre del campo padre para contexto
                extracted[f"{key}.{next(iter(nested))}"] = nested[next(iter(nested))]
                for nested_key, nested_value in list(nested.items())[1:]:
                    extracted[f"{key}.{nested_key}"] = nested_value
    
    return extracted


def extract_audit_fields(provider: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae solo campos de auditoría usando whitelist estricta.
    
    BLOQUE D: Este es el método principal. Solo retorna campos
    explícitamente permitidos para auditoría, sin PII.
    
    Args:
        provider: Nombre del proveedor (stripe/paypal)
        payload: Payload completo del webhook
    
    Returns:
        Dict con solo campos de auditoría
    """
    audit = {
        "provider": provider.lower(),
    }
    
    # Extraer campos usando whitelist
    extracted = _extract_whitelisted_fields(payload)
    audit.update(extracted)
    
    return audit


def sanitize_webhook_payload(
    provider: str,
    payload: Dict[str, Any],
    *,
    include_hash: bool = True,
    raw_payload: bytes | str | None = None,
) -> Dict[str, Any]:
    """
    BLOQUE D+: Prepara payload para persistencia usando whitelist + hash + core fields.
    
    En lugar de sanitizar por blacklist (puede escapar PII), usamos:
    - Whitelist estricta: solo campos explícitamente permitidos
    - Core fields: campos mínimos por provider (siempre si existen)
    - Hash del payload original para trazabilidad
    
    Args:
        provider: Nombre del proveedor (stripe/paypal)
        payload: Diccionario del payload parseado
        include_hash: Si incluir hash del payload original
        raw_payload: Payload original (para calcular hash)
    
    Returns:
        Payload seguro para persistir (sin PII)
    """
    # D+ HARDENING: Extraer core fields primero (siempre)
    safe_payload = _extract_core_fields(provider, payload)
    
    # Extraer campos de whitelist adicionales
    whitelist_fields = extract_audit_fields(provider, payload)
    
    # Merge: core fields tienen prioridad
    for key, value in whitelist_fields.items():
        if key not in safe_payload:
            safe_payload[key] = value
    
    # Agregar metadatos de procesamiento
    safe_payload["__provider__"] = provider.lower()
    safe_payload["__sanitized__"] = True
    safe_payload["__whitelist_version__"] = "1.1"  # Bump version for D+ hardening
    
    # Agregar hash del payload original para trazabilidad
    if include_hash:
        if raw_payload is not None:
            safe_payload["__payload_hash__"] = compute_payload_hash(raw_payload)
        else:
            safe_payload["__payload_hash__"] = compute_payload_hash(payload)
    
    original_fields = len(payload)
    safe_fields = len([k for k in safe_payload if not k.startswith("__")])
    core_fields_count = len([k for k in safe_payload if k.startswith("core.")])
    
    logger.debug(
        f"Payload procesado para {provider}: "
        f"{original_fields} campos originales -> {safe_fields} campos de auditoría "
        f"({core_fields_count} core fields)"
    )
    
    return safe_payload


# Legacy alias para compatibilidad (deprecated)
PII_FIELDS: Set[str] = set()  # Ya no se usa, pero mantenemos para imports existentes
ALLOWED_FIELDS = AUDIT_FIELDS_WHITELIST  # Alias para compatibilidad


__all__ = [
    "sanitize_webhook_payload",
    "extract_audit_fields",
    "compute_payload_hash",
    "AUDIT_FIELDS_WHITELIST",
    "CORE_FIELD_MAPPINGS",
    "PII_FIELDS",  # Legacy
    "ALLOWED_FIELDS",  # Legacy alias
]

# Fin del archivo backend/app/modules/payments/services/webhooks/payload_sanitizer.py
