
# -*- coding: utf-8 -*-
"""
backend/app/modules/files/metrics/__init__.py

Módulo de métricas de Files (Files v2).

Incluye:
- Aggregators (DB y memoria)
- Collectors (in-memory)
- Exporters (Prometheus)
- Schemas (TypedDict para snapshot v2)
- Rutas en `routes/` para exponer métricas vía API

NOTA IMPORTANTE:
Este módulo NO exporta routers directamente. Las rutas deben ser 
incluidas por `backend/app/modules/files/metrics/routes/__init__.py`, 
que actúa como el ensamblador oficial de endpoints.

Autor: Ixchel Beristáin Mendoza
Fecha: 2025-11-22
"""

# No se requieren exports a nivel módulo.
# Aunque podríamos exportar tipos si alguna parte de la app lo necesitara,
# la práctica en DoxAI v2 es mantener este `__init__` solo como namespace.

__all__: list[str] = []

# Fin del archivo backend/app/modules/files/metrics/__init__.py
