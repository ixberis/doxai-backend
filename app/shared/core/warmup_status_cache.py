# -*- coding: utf-8 -*-
"""
backend/app/shared/core/warmup_status_cache.py

Estado y dataclass para el seguimiento del proceso de warm-up.
Proporciona observabilidad completa del estado de inicialización.

Autor: Ixchel Beristain
Fecha: 05/09/2025
Actualizado:
- 2025-10-24: Extraído de resource_cache.py para mejor modularidad
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WarmupStatus:
    """Estado del warm-up con observabilidad completa."""
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    duration_sec: Optional[float] = None
    fast_ok: bool = False
    hires_ok: bool = False
    table_model_ok: bool = False
    http_client_ok: bool = False
    http_health_ok: bool = False
    tesseract_ok: bool = True  # assume true; detect and set false if missing
    ghostscript_ok: bool = False
    ghostscript_path: Optional[str] = None
    poppler_ok: bool = False
    poppler_path: Optional[str] = None
    http_health_latency_ms: Optional[float] = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """Determina si el sistema está listo para operar."""
        return self.fast_ok and self.http_client_ok


# Fin del archivo backend/app/shared/core/warmup_status_cache.py
