
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/metrics_schemas.py

Esquemas Pydantic para métricas del módulo Auth.

Define estructuras de salida limpias (sin PII) para
exponer snapshots de métricas al panel administrativo.

Autor: Ixchel Beristain
Fecha: 2025-11-07
"""
from typing import Optional
from pydantic import BaseModel


class AuthMetricsSnapshot(BaseModel):
    """Snapshot de métricas derivadas del módulo Auth."""
    active_sessions: Optional[int] = None
    activation_conversion_ratio: Optional[float] = None
    partial: bool = False  # True if some metrics failed to load


# Fin del archivo backend/app/modules/auth/metrics/schemas/metrics_schemas.py
