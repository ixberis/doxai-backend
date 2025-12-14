# -*- coding: utf-8 -*-
"""
backend/app/__init__.py

Inicializador del paquete principal 'app' del backend DoxAI.

Funciones:
- Asegura compatibilidad del event loop de asyncio en Windows
  (necesario para compatibilidad con psycopg[async] y SQLAlchemy Async).
- Permite que los módulos internos puedan importarse como 'app.*'
  cuando la carpeta 'backend' se incluye en PYTHONPATH.

Autor: Ixchel Beristain
Fecha: 2025-11-07
"""
import sys
import asyncio

# Fuerza un event loop compatible con psycopg async en Windows
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        # Si ya hay un loop activo, ignora silenciosamente
        pass

# Fin del archivo backend/app/__init__.py









