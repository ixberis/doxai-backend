
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/time_window.py

Enum con ventanas de tiempo para agregación.

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from enum import Enum


class TimeWindow(str, Enum):
    """Ventanas de tiempo para agregación de métricas en memoria."""
    MINUTE = "1m"
    HOUR = "1h"
    DAY = "1d"

# Fin del archivo backend\app\modules\payments\metrics\aggregators\time_window.py