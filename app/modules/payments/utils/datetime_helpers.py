# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/utils/datetime_helpers.py

Utilidades para manejo consistente de timestamps ISO 8601.

Autor: Ixchel Beristáin
Fecha: 26/10/2025
"""

from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    """
    Retorna el timestamp UTC actual (timezone-aware).
    
    Returns:
        datetime UTC actual con tzinfo=timezone.utc
    
    Examples:
        >>> now = utcnow()
        >>> now.tzinfo == timezone.utc
        True
    """
    return datetime.now(timezone.utc)


def from_iso8601(iso_string: str) -> datetime:
    """
    Parsea una cadena ISO 8601 y retorna datetime UTC timezone-aware.
    
    Args:
        iso_string: Cadena ISO 8601 (con o sin zona horaria)
    
    Returns:
        datetime UTC timezone-aware
    
    Examples:
        >>> dt = from_iso8601("2025-10-26T14:30:00Z")
        >>> dt.tzinfo == timezone.utc
        True
        >>> dt = from_iso8601("2025-10-26T14:30:00-06:00")
        >>> dt.tzinfo == timezone.utc
        True
    """
    dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
    # Convertir a UTC si tiene otra zona horaria
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        dt = dt.astimezone(timezone.utc)
    return dt


def ensure_utc(dt: datetime) -> datetime:
    """
    Asegura que un datetime sea UTC timezone-aware.
    
    Args:
        dt: datetime a convertir
    
    Returns:
        datetime UTC timezone-aware
    
    Examples:
        >>> from datetime import timezone, timedelta
        >>> dt_naive = datetime(2025, 10, 26, 14, 30, 0)
        >>> dt_utc = ensure_utc(dt_naive)
        >>> dt_utc.tzinfo == timezone.utc
        True
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        return dt.astimezone(timezone.utc)
    return dt


def to_iso8601(dt: Optional[datetime]) -> Optional[str]:
    """
    Convierte datetime a string ISO 8601 con 'Z' para UTC.
    
    Args:
        dt: datetime a convertir (debe ser timezone-aware en UTC)
    
    Returns:
        String ISO 8601 con 'Z' (ej: "2025-10-26T14:30:00Z") o None si dt es None
    
    Examples:
        >>> from datetime import datetime, timezone
        >>> dt = datetime(2025, 10, 26, 14, 30, 0, tzinfo=timezone.utc)
        >>> to_iso8601(dt)
        '2025-10-26T14:30:00Z'
    """
    if dt is None:
        return None
    return dt.isoformat().replace('+00:00', 'Z')


__all__ = ["utcnow", "to_iso8601", "from_iso8601", "ensure_utc"]
# Fin del archivo
