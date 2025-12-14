
# -*- coding: utf-8 -*-
"""
backend/app/modules/payments/metrics/aggregators/utils.py

Utilidades auxiliares para métricas (p. ej., percentiles).

Autor: Ixchel Beristáin
Fecha: 08/11/2025
"""

from typing import List


def percentile_linear_interp(sorted_data: List[float], p: float) -> float:
    """
    Calcula el percentil `p` (0..1) con interpolación lineal.

    Requiere que `sorted_data` esté previamente ordenado ascendentemente.
    """
    n = len(sorted_data)
    if n == 0:
        return 0.0
    k = (n - 1) * p
    f = int(k)
    c = f + 1
    if c >= n:
        return float(sorted_data[-1])
    d0 = float(sorted_data[f])
    d1 = float(sorted_data[c])
    return d0 + (d1 - d0) * (k - f)
# Fin del archivo backend\app\modules\payments\metrics\aggregators\utils.py