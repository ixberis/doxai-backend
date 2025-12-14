# -*- coding: utf-8 -*-
"""
backend/app/shared/core/resources_cache.py

Contenedor singleton de recursos globales compartidos.
Mantiene estado de HTTP client, modelos y estado de warm-up.

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 2025-10-24: Extraído de resource_cache.py para mejor modularidad
"""

from __future__ import annotations
from typing import Optional, Any
import asyncio
import httpx

from .warmup_status_cache import WarmupStatus


class GlobalResources:
    """Contenedor de recursos globales compartidos (instancia única por proceso)."""

    def __init__(self) -> None:
        self.http_client: Optional[httpx.AsyncClient] = None
        self.warmup_status: WarmupStatus = WarmupStatus()
        self.warmup_completed: bool = False
        # Nota: Los singletons de modelos (_table_agent, _fast_parser) ahora viven
        # completamente en model_singletons_cache.py y usan el cache interno de
        # Unstructured. Estos campos fueron removidos para evitar confusión.


# Instancia singleton de recursos globales
resources = GlobalResources()
_warmup_lock = asyncio.Lock()


def get_warmup_status() -> WarmupStatus:
    """Obtiene el estado actual del warm-up sin ejecutarlo."""
    return resources.warmup_status


# Fin del archivo backend/app/shared/core/resources_cache.py
