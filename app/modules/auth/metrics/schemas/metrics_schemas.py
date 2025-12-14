
# -*- coding: utf-8 -*-
"""
backend/app/modules/auth/metrics/schemas/metrics_schemas.py

Esquemas Pydantic para métricas del módulo Auth.

Define estructuras de salida limpias (sin PII) para
exponer snapshots de métricas al panel administrativo.

Autor: Ixchel Beristain
Fecha: 2025-11-07
"""
from pydantic import BaseModel


class AuthMetricsSnapshot(BaseModel):
    """Snapshot de métricas derivadas del módulo Auth."""
    active_sessions: int
    activation_conversion_ratio: float


# Fin del archivo backend/app/modules/auth/metrics/schemas/metrics_schemas.py
