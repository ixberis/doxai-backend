# -*- coding: utf-8 -*-
"""
backend/app/shared/diagnostics/__init__.py

Módulo de utilidades de diagnóstico.

Autor: DoxAI
Fecha: 2026-01-11
"""

from .model_table_check import (
    run_wallet_table_diagnostic,
    log_wallet_model_config,
)

__all__ = [
    "run_wallet_table_diagnostic",
    "log_wallet_model_config",
]
