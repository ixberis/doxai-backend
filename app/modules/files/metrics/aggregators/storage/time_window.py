
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/aggregators/storage/time_window.py

Helper de ventanas de tiempo para snapshots (7d, 30d, 90d).

Autor: Ixchel Beristáin Mendoza
Fecha: 09/11/2025
"""
from __future__ import annotations


def clamp_days(days: int | None, default: int = 30, max_days: int = 365) -> int:
    if days is None:
        return default
    try:
        d = int(days)
    except Exception:
        return default
    return max(1, min(d, max_days))


# Fin del archivo backend/app/modules/files/metrics/aggregators/storage/time_window.py
